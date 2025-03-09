import json
import logging
import math
from collections import namedtuple
from enum import Enum
from random import randint
from typing import Callable, Tuple
from zoneinfo import ZoneInfo

import arrow
import redis
import requests
import sentry_sdk
from furl import furl
from pymongo import ASCENDING, GEOSPHERE, MongoClient
from timezonefinder import TimezoneFinder

from settings import GOOGLE_API_KEY, MONGODB_URL, REDIS_URL
from winds_mobi_provider.logging import configure_logging
from winds_mobi_provider.units import Pressure, ureg
from winds_mobi_provider.uwxutils import TWxUtils

configure_logging()


class StationStatus(Enum):
    HIDDEN = "hidden"
    RED = "red"
    ORANGE = "orange"
    GREEN = "green"


StationNames = namedtuple("StationNames", ["short_name", "name"])


class Provider:
    provider_code = None
    provider_name = None
    provider_url = None

    connect_timeout = 7
    read_timeout = 30

    @property
    def usage_limit_cache_duration(self):
        return (12 + randint(-2, 2)) * 3600

    @property
    def google_api_error_cache_duration(self):
        return (30 + randint(-5, 5)) * 24 * 3600

    @property
    def google_api_cache_duration(self):
        return (60 + randint(-5, 5)) * 24 * 3600

    def __init__(self):
        if None in (self.provider_code, self.provider_name, self.provider_url):
            raise ProviderException("Missing provider_code, provider_name or provider_url")
        self.mongo_db = MongoClient(MONGODB_URL).get_database()
        self.__stations_collection = self.mongo_db.stations
        self.__stations_collection.create_index(
            [
                ("loc", GEOSPHERE),
                ("status", ASCENDING),
                ("pv-code", ASCENDING),
                ("short", ASCENDING),
                ("name", ASCENDING),
            ]
        )
        self.collection_names = self.mongo_db.list_collection_names()
        self.redis = redis.StrictRedis.from_url(url=REDIS_URL, decode_responses=True)
        self.google_api_key = GOOGLE_API_KEY
        self.timezone_finder = TimezoneFinder(in_memory=True)
        self.log = logging.getLogger(self.provider_code)
        sentry_sdk.set_tag("provider", self.provider_code)

    def stations_collection(self):
        return self.__stations_collection

    def measures_collection(self, station_id):
        if station_id not in self.collection_names:
            self.mongo_db.create_collection(station_id)
            self.mongo_db[station_id].create_index([("time", ASCENDING)], expireAfterSeconds=60 * 60 * 24 * 10)
            self.collection_names.append(station_id)
        return self.mongo_db[station_id]

    def __to_wind_direction(self, value):
        if isinstance(value, ureg.Quantity):
            return to_int(value.to(ureg.degree).magnitude, mandatory=True)
        else:
            return to_int(value, mandatory=True)

    def __to_wind_speed(self, value):
        if isinstance(value, ureg.Quantity):
            return to_float(value.to(ureg.kilometer / ureg.hour).magnitude, mandatory=True)
        else:
            return to_float(value, mandatory=True)

    def __to_temperature(self, value):
        if isinstance(value, ureg.Quantity):
            return to_float(value.to(ureg.degC).magnitude)
        else:
            return to_float(value)

    def __to_pressure(self, value):
        if isinstance(value, ureg.Quantity):
            return to_float(value.to(ureg.hPa).magnitude, ndigits=4)
        else:
            return to_float(value, ndigits=4)

    def __compute_pressures(self, p: Pressure, altitude, temperature, humidity):
        # Normalize pressure to HPa
        qfe = self.__to_pressure(p.qfe)
        qnh = self.__to_pressure(p.qnh)
        qff = self.__to_pressure(p.qff)

        if qfe and qnh is None:
            qnh = TWxUtils.StationToAltimeter(qfe, elevationM=altitude)

        if qnh and qfe is None:
            qfe = TWxUtils.AltimeterToStationPressure(qnh, elevationM=altitude)

        if qfe and qff is None and temperature is not None and humidity is not None:
            qff = TWxUtils.StationToSeaLevelPressure(
                qfe, elevationM=altitude, currentTempC=temperature, meanTempC=temperature, humidity=humidity
            )
        if qff and qfe is None and temperature is not None and humidity is not None:
            qfe = TWxUtils.SeaLevelToStationPressure(
                qff, elevationM=altitude, currentTempC=temperature, meanTempC=temperature, humidity=humidity
            )

        return {"qfe": to_float(qfe), "qnh": to_float(qnh), "qff": to_float(qff)}

    def __to_altitude(self, value):
        if isinstance(value, ureg.Quantity):
            return to_int(value.to(ureg.meter).magnitude)
        else:
            return to_int(value)

    def __to_rain(self, value):
        if isinstance(value, ureg.Quantity):
            return to_float(value.to(ureg.liter / (ureg.meter**2)).magnitude, 1)
        else:
            return to_float(value, 1)

    def add_redis_key(self, key, values, cache_duration):
        pipe = self.redis.pipeline()
        pipe.hmset(key, values)
        pipe.expire(key, cache_duration)
        pipe.execute()

    def call_google_api(self, url, api_name):
        path = furl(url)
        path.args["key"] = self.google_api_key
        result = requests.get(path.url, timeout=(self.connect_timeout, self.read_timeout)).json()
        if result["status"] == "OVER_QUERY_LIMIT":
            raise UsageLimitException(f"[{api_name}] OVER_QUERY_LIMIT")
        elif result["status"] == "INVALID_REQUEST":
            if "error_message" in result:
                raise ProviderException(f"[{api_name}] INVALID_REQUEST: url='{url}', error='{result['error_message']}'")
            else:
                raise ProviderException(f"[{api_name}] INVALID_REQUEST: url='{url}'")
        elif result["status"] == "ZERO_RESULTS":
            raise ProviderException(f"[{api_name}] ZERO_RESULTS: url='{url}'")
        return result

    def __parse_reverse_geocoding_results(self, address_key: str) -> StationNames:
        cache = self.redis.hgetall(address_key)
        if error := cache.get("error"):
            self.log.warning(f"Unable to determine station names: {error}")
            return StationNames(None, None)

        address_types = [
            "airport",
            "locality",
            "colloquial_area",
            "natural_feature",
            "point_of_interest",
            "neighborhood",
            "sublocality",
            "administrative_area_level_3",
        ]

        def order_by_type(address):
            for address_type in address_types:
                if address_type in address["types"]:
                    try:
                        return address_types.index(address_type)
                    except ValueError:
                        pass
            return 100

        addresses = json.loads(cache["json"])["results"]
        addresses.sort(key=order_by_type)

        if len(addresses) > 0:
            for address_type in address_types:
                # Use the first address because they are ordered by importance
                for component in addresses[0]["address_components"]:
                    if address_type in component["types"]:
                        return StationNames(component["short_name"], component["long_name"])

        self.log.warning(f"Google Reverse Geocoding API: no address match for '{address_key}'")
        return StationNames(None, None)

    def __compute_elevation(self, lat, lon) -> Tuple[float, bool]:
        radius = 500
        nb = 6
        path = f"{lat},{lon}|"
        for k in range(nb):
            angle = math.pi * 2 * k / nb
            dx = radius * math.cos(angle)
            dy = radius * math.sin(angle)
            path += "{lat},{lon}".format(
                lat=str(lat + (180 / math.pi) * (dy / 6378137)),
                lon=str(lon + (180 / math.pi) * (dx / 6378137) / math.cos(lat * math.pi / 180)),
            )
            if k < nb - 1:
                path += "|"

        result = self.call_google_api(
            f"https://maps.googleapis.com/maps/api/elevation/json?locations={path}", "Google Elevation API"
        )
        elevation = float(result["results"][0]["elevation"])
        is_peak = False
        for point in result["results"][1:]:
            try:
                glide_ratio = radius / (elevation - float(point["elevation"]))
            except ZeroDivisionError:
                glide_ratio = float("Infinity")
            if 0 < glide_ratio < 6:
                is_peak = True
                break
        return elevation, is_peak

    def get_station_id(self, provider_id):
        return self.provider_code + "-" + str(provider_id)

    def __create_station(
        self, provider_id, short_name, name, latitude, longitude, altitude, is_peak, status, timezone, urls, fixes
    ):
        if fixes is None:
            fixes = {}

        if any(
            (not short_name, not name, altitude is None, latitude is None, longitude is None, not status, not timezone)
        ):
            raise ProviderException("A mandatory value is none!")

        station = {
            "pv-id": provider_id,
            "pv-code": self.provider_code,
            "pv-name": self.provider_name,
            "url": urls,
            "short": fixes.get("short") or short_name,
            "name": fixes.get("name") or name,
            "alt": self.__to_altitude(fixes["alt"] if "alt" in fixes else altitude),
            "peak": to_bool(fixes["peak"] if "peak" in fixes else is_peak),
            "loc": {
                "type": "Point",
                "coordinates": [
                    to_float(fixes["longitude"] if "longitude" in fixes else longitude, 6),
                    to_float(fixes["latitude"] if "latitude" in fixes else latitude, 6),
                ],
            },
            "status": status,
            "tz": timezone.key,
            "seen": arrow.utcnow().int_timestamp,  # deprecated
            "lastSeenAt": arrow.utcnow().datetime,
        }
        return station

    def save_station(
        self,
        provider_id,
        names: StationNames | Callable[[StationNames], StationNames],
        latitude,
        longitude,
        status: StationStatus,
        altitude=None,
        timezone: ZoneInfo = None,
        url=None,
    ):
        if provider_id is None:
            raise ProviderException("Missing provider_id")
        station_id = self.get_station_id(provider_id)

        lat = to_float(latitude, 6)
        lon = to_float(longitude, 6)
        if lat is None or lon is None:
            raise ProviderException("Missing latitude or longitude")
        if lat < -90 or lat > 90 or lon < -180 or lon > 180:
            raise ProviderException(f"Invalid latitude '{lat}' or longitude '{lon}'")

        if isinstance(names, StationNames):
            short_name, name = names
        elif callable(names):
            address_key = f"address2/{lat},{lon}"
            if not self.redis.exists(address_key):
                try:
                    result = self.call_google_api(
                        f"https://maps.googleapis.com/maps/api/geocode/json?latlng={lat},{lon}",
                        "Google Reverse Geocoding API",
                    )
                    self.add_redis_key(
                        address_key,
                        {"json": json.dumps(result)},
                        self.google_api_cache_duration,
                    )
                except TimeoutError as e:
                    raise e
                except UsageLimitException as e:
                    self.add_redis_key(address_key, {"error": repr(e)}, self.usage_limit_cache_duration)
                except Exception as e:
                    if not isinstance(e, ProviderException):
                        self.log.exception("Unable to call Google Reverse Geocoding API")
                    self.add_redis_key(address_key, {"error": repr(e)}, self.google_api_error_cache_duration)

            short_name, name = names(self.__parse_reverse_geocoding_results(address_key))
        else:
            raise ProviderException(f"Invalid station names '{names}'")
        if not short_name or not name:
            raise ProviderException(f"Invalid station short_name '{short_name}' or name '{name}'")

        alt_key = f"alt/{lat},{lon}"
        if not self.redis.exists(alt_key):
            try:
                elevation, is_peak = self.__compute_elevation(lat, lon)
                self.add_redis_key(alt_key, {"alt": elevation, "is_peak": str(is_peak)}, self.google_api_cache_duration)
            except TimeoutError as e:
                raise e
            except UsageLimitException as e:
                self.add_redis_key(alt_key, {"error": repr(e)}, self.usage_limit_cache_duration)
            except Exception as e:
                if not isinstance(e, ProviderException):
                    self.log.exception("Unable to call Google Elevation API")
                self.add_redis_key(alt_key, {"error": repr(e)}, self.google_api_error_cache_duration)

        if not altitude:
            if self.redis.hexists(alt_key, "error"):
                raise ProviderException(
                    f"Unable to determine station 'alt': " f"{self.redis.hget(alt_key, 'error')} for '{alt_key}'"
                )
            altitude = self.redis.hget(alt_key, "alt")

        if self.redis.hexists(alt_key, "error") == "error":
            raise ProviderException(
                f"Unable to determine station 'peak': " f"{self.redis.hget(alt_key, 'error')} for '{alt_key}'"
            )
        is_peak = self.redis.hget(alt_key, "is_peak") == "True"

        if not timezone:
            try:
                timezone = ZoneInfo(self.timezone_finder.timezone_at(lng=lon, lat=lat))
            except Exception as e:
                raise ProviderException("Unable to determine station 'time_zone'") from e

        if not url:
            urls = {"default": self.provider_url}
        elif isinstance(url, str):
            urls = {"default": url}
        elif isinstance(url, dict):
            if "default" not in url:
                raise ProviderException("No 'default' key in url")
            urls = url
        else:
            raise ProviderException("Invalid url")

        fixes = self.mongo_db.stations_fix.find_one(station_id)
        station = self.__create_station(
            provider_id, short_name, name, lat, lon, altitude, is_peak, status.value, timezone, urls, fixes
        )
        self.stations_collection().update_one({"_id": station_id}, {"$set": station}, upsert=True)
        station["_id"] = station_id
        return station

    def create_measure(
        self,
        for_station,
        _id,
        wind_direction,
        wind_average,
        wind_maximum,
        temperature=None,
        humidity=None,
        pressure: Pressure = None,
        rain=None,
    ):
        if all((wind_direction is None, wind_average is None, wind_maximum is None)):
            raise ProviderException("All mandatory values are null!")

        measure = {
            "_id": int(round(_id)),
            # Mandatory values: 0 if not present
            "w-dir": self.__to_wind_direction(wind_direction),
            "w-avg": self.__to_wind_speed(wind_average),
            "w-max": self.__to_wind_speed(wind_maximum),
        }

        # Optional keys
        if temperature is not None:
            measure["temp"] = self.__to_temperature(temperature)
        if humidity is not None:
            measure["hum"] = to_float(humidity, 1)
        if pressure is not None and (pressure.qfe is not None or pressure.qnh is not None or pressure.qff is not None):
            measure["pres"] = self.__compute_pressures(
                pressure, for_station["alt"], measure.get("temp", None), measure.get("hum", None)
            )
        if rain is not None:
            measure["rain"] = self.__to_rain(rain)

        measure["time"] = arrow.get(measure["_id"]).datetime
        measure["receivedAt"] = arrow.utcnow().datetime

        fixes = self.mongo_db.stations_fix.find_one(for_station["_id"])
        if fixes and "measures" in fixes:
            for key, offset in fixes["measures"].items():
                try:
                    if key in measure:
                        fixed_value = measure[key] + offset
                        if key == "w-dir":
                            fixed_value = fixed_value % 360
                        measure[key] = fixed_value

                except Exception as e:
                    self.log.exception(f"Unable to fix '{key}' with offset '{offset}': {e}")

        return measure

    def has_measure(self, measure_collection, key):
        return measure_collection.count_documents({"_id": key}) > 0

    def __add_last_measure(self, measure_collection, station_id):
        last_measure = measure_collection.find_one({"$query": {}, "$orderby": {"_id": -1}})
        if last_measure:
            self.stations_collection().update_one({"_id": station_id}, {"$set": {"last": last_measure}})

    def insert_new_measures(self, measure_collection, station, new_measures):
        if len(new_measures) > 0:
            measure_collection.insert_many(sorted(new_measures, key=lambda m: m["_id"]))

            end_date = arrow.Arrow.fromtimestamp(new_measures[-1]["_id"], ZoneInfo(station["tz"]))
            self.log.info(
                "⏱ {end_date} ({end_date_local}) '{short}'/'{name}' ({id}): {nb} values inserted".format(
                    end_date=end_date.format("YY-MM-DD HH:mm:ssZZ"),
                    end_date_local=end_date.to("local").format("YY-MM-DD HH:mm:ssZZ"),
                    short=station["short"],
                    name=station["name"],
                    id=station["_id"],
                    nb=str(len(new_measures)),
                )
            )

            self.__add_last_measure(measure_collection, station["_id"])


class ProviderException(Exception):
    pass


class UsageLimitException(ProviderException):
    pass


def to_int(value, mandatory=False):
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        if mandatory:
            return 0
        return None


def to_float(value, ndigits=1, mandatory=False):
    try:
        return round(float(value), ndigits)
    except (TypeError, ValueError):
        if mandatory:
            return 0.0
        return None


def to_bool(value):
    return str(value).lower() in ["true", "yes"]
