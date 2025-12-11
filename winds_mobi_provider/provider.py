import json
import logging
import math
from collections import namedtuple
from collections.abc import Callable
from enum import Enum
from zoneinfo import ZoneInfo

import arrow
import redis
import requests
import sentry_sdk
from furl import furl
from pymongo import ASCENDING, GEOSPHERE, MongoClient
from sentry_sdk import metrics
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

    __api_limit_cache_duration = 3600
    __api_error_cache_duration = 30 * 24 * 3600
    __api_cache_duration = 3 * 30 * 24 * 3600

    def __init__(self):
        if None in (self.provider_code, self.provider_name, self.provider_url):
            raise ProviderException("Missing provider_code, provider_name or provider_url")
        self.mongo_db = MongoClient(MONGODB_URL).get_database()
        self.__providers_collection = self.mongo_db.providers
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

    def __create_measures_collection(self, station_id):
        if station_id not in self.collection_names:
            self.mongo_db.create_collection(station_id)
            self.mongo_db[station_id].create_index([("time", ASCENDING)], expireAfterSeconds=60 * 60 * 24 * 10)
            self.collection_names.append(station_id)

    def __measures_collection(self, station_id):
        return self.mongo_db[station_id]

    def __to_int(self, value, mandatory=False):
        try:
            return int(round(float(value)))
        except (TypeError, ValueError):
            if mandatory:
                return 0
            return None

    def __to_float(self, value, ndigits=1, mandatory=False):
        try:
            return round(float(value), ndigits)
        except (TypeError, ValueError):
            if mandatory:
                return 0.0
            return None

    def __to_bool(self, value):
        return str(value).lower() in ["true", "yes"]

    def __to_wind_direction(self, value):
        if isinstance(value, ureg.Quantity):
            return self.__to_int(value.to(ureg.degree).magnitude, mandatory=True)
        else:
            return self.__to_int(value, mandatory=True)

    def __to_wind_speed(self, value):
        if isinstance(value, ureg.Quantity):
            return self.__to_float(value.to(ureg.kilometer / ureg.hour).magnitude, mandatory=True)
        else:
            return self.__to_float(value, mandatory=True)

    def __to_temperature(self, value):
        if isinstance(value, ureg.Quantity):
            return self.__to_float(value.to(ureg.degC).magnitude)
        else:
            return self.__to_float(value)

    def __to_pressure(self, value):
        if isinstance(value, ureg.Quantity):
            return self.__to_float(value.to(ureg.hPa).magnitude, ndigits=4)
        else:
            return self.__to_float(value, ndigits=4)

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

        return {"qfe": self.__to_float(qfe), "qnh": self.__to_float(qnh), "qff": self.__to_float(qff)}

    def __to_altitude(self, value):
        if isinstance(value, ureg.Quantity):
            return self.__to_int(value.to(ureg.meter).magnitude)
        else:
            return self.__to_int(value)

    def __to_rain(self, value):
        if isinstance(value, ureg.Quantity):
            return self.__to_float(value.to(ureg.liter / (ureg.meter**2)).magnitude, 1)
        else:
            return self.__to_float(value, 1)

    def __add_redis_key(self, key, values, cache_duration):
        pipe = self.redis.pipeline()
        pipe.hset(key, mapping=values)
        pipe.expire(key, cache_duration)
        pipe.execute()

    def __call_google_api(self, url, api_name):
        path = furl(url)
        path.args["key"] = self.google_api_key
        metrics.count("api.call", 1, attributes={"name": api_name, "provider": self.provider_code})
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

    def __get_station_names_from_geocoding_results(self, address_key: str, results: list) -> StationNames:
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

        addresses = sorted(results, key=order_by_type)
        if len(addresses) > 0:
            for address_type in address_types:
                # Use the first address because they are ordered by importance
                for component in addresses[0]["address_components"]:
                    if address_type in component["types"]:
                        return StationNames(component["short_name"], component["long_name"])

        self.log.warning(f"Google Geocoding API: no address match for '{address_key}'")
        return StationNames(None, None)

    def __get_country_code_from_geocoding_results(self, address_key: str, results: list) -> str | None:
        for address in results:
            if "country" in address["types"]:
                return address["address_components"][0]["short_name"]
        self.log.warning(f"Google Geocoding API: no country match for '{address_key}'")
        return None

    def __compute_elevation(self, lat: float, lon: float) -> tuple[float, bool]:
        radius = 500
        nb = 6
        path = f"{lat},{lon}|"
        for k in range(nb):
            angle = math.pi * 2 * k / nb
            dx = radius * math.cos(angle)
            dy = radius * math.sin(angle)
            lat = lat + (180 / math.pi) * (dy / 6378137)
            lon = lon + (180 / math.pi) * (dx / 6378137) / math.cos(lat * math.pi / 180)
            path += f"{lat:.6f},{lon:.6f}"
            if k < nb - 1:
                path += "|"

        result = self.__call_google_api(
            f"https://maps.googleapis.com/maps/api/elevation/json?locations={path}", "Google Maps Elevation API"
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

    def __haversine_distance(self, lat1, lon1, lat2, lon2):
        # Radius of the Earth in km
        radius = 6371.0

        # Convert degrees to radians
        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)
        delta_phi = math.radians(lat2 - lat1)
        delta_lambda = math.radians(lon2 - lon1)

        # Haversine formula
        a = math.sin(delta_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2

        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

        distance = radius * c
        return distance

    def __coordinates_changed(self, station_id, lat2, lon2):
        coordinates = self.__stations_collection.find_one(station_id, projection={"loc.coordinates": True})
        if coordinates:
            lon1, lat1 = coordinates["loc"]["coordinates"]
            distance = self.__haversine_distance(lat1, lon1, lat2, lon2)
            if distance < 5:
                return False
        return True

    def get_station_id(self, provider_id):
        return self.provider_code + "-" + str(provider_id)

    def __create_station(
        self,
        provider_id,
        short_name,
        name,
        latitude,
        longitude,
        altitude,
        is_peak,
        status,
        country_code,
        timezone,
        urls,
        fixes,
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
            "alt": self.__to_altitude(fixes.get("alt", altitude)),
            "peak": self.__to_bool(fixes.get("peak", is_peak)),
            "loc": {
                "type": "Point",
                "coordinates": [
                    self.__to_float(fixes.get("longitude", longitude), 6),
                    self.__to_float(fixes.get("latitude", latitude), 6),
                ],
            },
            "status": status,
            "country": country_code,
            "tz": timezone.key,
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
    ) -> dict:
        if provider_id is None:
            raise ProviderException("Missing provider_id")
        station_id = self.get_station_id(provider_id)

        lat = self.__to_float(latitude, 6)
        lon = self.__to_float(longitude, 6)
        if lat is None or lon is None:
            raise ProviderException("Missing latitude or longitude")
        if lat < -90 or lat > 90 or lon < -180 or lon > 180:
            raise ProviderException(f"Invalid latitude '{lat}' or longitude '{lon}'")

        country_code = None
        if isinstance(names, StationNames):
            short_name, name = names
        elif callable(names):
            address_key = f"address2/{lat},{lon}"
            if not self.redis.exists(address_key) and self.__coordinates_changed(station_id, lat, lon):
                try:
                    result = self.__call_google_api(
                        f"https://maps.googleapis.com/maps/api/geocode/json?latlng={lat},{lon}",
                        "Google Geocoding API",
                    )
                    self.__add_redis_key(
                        address_key,
                        {"json": json.dumps(result)},
                        self.__api_cache_duration,
                    )
                except TimeoutError as e:
                    raise e
                except UsageLimitException as e:
                    self.__add_redis_key(address_key, {"error": repr(e)}, self.__api_limit_cache_duration)
                except Exception as e:
                    if not isinstance(e, ProviderException):
                        self.log.exception("Unable to call Google Geocoding API")
                    self.__add_redis_key(address_key, {"error": repr(e)}, self.__api_error_cache_duration)

            cache = self.redis.hgetall(address_key)
            if error := cache.get("error"):
                raise ProviderException(f"Unable to get station geocoding for '{address_key}': {error}")
            results = json.loads(cache["json"])["results"]
            short_name, name = names(self.__get_station_names_from_geocoding_results(address_key, results))
            country_code = self.__get_country_code_from_geocoding_results(address_key, results)
        else:
            raise ProviderException(f"Invalid station names '{names}'")
        if not short_name or not name:
            raise ProviderException(f"Invalid station short_name '{short_name}' or name '{name}'")

        alt_key = f"alt/{lat},{lon}"
        if not self.redis.exists(alt_key) and self.__coordinates_changed(station_id, lat, lon):
            try:
                elevation, is_peak = self.__compute_elevation(lat, lon)
                self.__add_redis_key(alt_key, {"alt": elevation, "is_peak": str(is_peak)}, self.__api_cache_duration)
            except TimeoutError as e:
                raise e
            except UsageLimitException as e:
                self.__add_redis_key(alt_key, {"error": repr(e)}, self.__api_limit_cache_duration)
            except Exception as e:
                if not isinstance(e, ProviderException):
                    self.log.exception("Unable to call Google Elevation API")
                self.__add_redis_key(alt_key, {"error": repr(e)}, self.__api_error_cache_duration)

        cache = self.redis.hgetall(alt_key)
        if error := cache.get("error"):
            raise ProviderException(f"Unable to get station elevation for '{alt_key}': {error}")
        if not altitude:
            altitude = cache["alt"]
        is_peak = cache["is_peak"] == "True"

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
            provider_id,
            short_name,
            name,
            lat,
            lon,
            altitude,
            is_peak,
            status.value,
            country_code,
            timezone,
            urls,
            fixes,
        )
        self.__stations_collection.update_one({"_id": station_id}, {"$set": station}, upsert=True)
        self.__create_measures_collection(station_id)
        station["_id"] = station_id
        return station

    def create_measure(
        self,
        station,
        _id,
        wind_direction,
        wind_average,
        wind_maximum,
        temperature=None,
        humidity=None,
        pressure: Pressure = None,
        rain=None,
    ) -> dict:
        if all((wind_direction is None, wind_average is None, wind_maximum is None)):
            raise ProviderException("All mandatory values are null!")

        measure: dict = {
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
            measure["hum"] = self.__to_float(humidity, 1)
        if pressure is not None and (pressure.qfe is not None or pressure.qnh is not None or pressure.qff is not None):
            measure["pres"] = self.__compute_pressures(
                pressure, station["alt"], measure.get("temp"), measure.get("hum")
            )
        if rain is not None:
            measure["rain"] = self.__to_rain(rain)

        measure["time"] = arrow.get(measure["_id"]).datetime
        measure["receivedAt"] = arrow.utcnow().datetime

        fixes = self.mongo_db.stations_fix.find_one(station["_id"])
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

    def has_measure(self, station: dict, timestamp: int) -> bool:
        return self.__measures_collection(station["_id"]).count_documents({"_id": timestamp}) > 0

    def __add_last_measure(self, measures_collection, station_id):
        last_measure = measures_collection.find_one({"$query": {}, "$orderby": {"_id": -1}})
        if last_measure:
            self.__stations_collection.update_one({"_id": station_id}, {"$set": {"last": last_measure}})

    def insert_measures(self, station: dict, measures: list[dict] | dict):
        if not isinstance(measures, list):
            measures = [measures]

        if len(measures) > 0:
            result = self.__measures_collection(station["_id"]).insert_many(measures, ordered=False)
            if len(result.inserted_ids) != len(measures):
                self.log.warning(f"{len(measures) - len(result.inserted_ids)} measure(s) not inserted")

            end_date = arrow.Arrow.fromtimestamp(measures[-1]["_id"], ZoneInfo(station["tz"]))
            self.log.info(
                "⏱ {end_date} ({end_date_local}) '{short}'/'{name}' ({id}): {nb} values inserted".format(
                    end_date=end_date.format("YY-MM-DD HH:mm:ssZZ"),
                    end_date_local=end_date.to("local").format("YY-MM-DD HH:mm:ssZZ"),
                    short=station["short"],
                    name=station["name"],
                    id=station["_id"],
                    nb=len(result.inserted_ids),
                )
            )

            self.__add_last_measure(self.__measures_collection(station["_id"]), station["_id"])
            now = arrow.utcnow()
            self.__providers_collection.update_one(
                {"_id": self.provider_code},
                {
                    "$set": {"name": self.provider_name, "url": self.provider_url, "lastSeenAt": now.datetime},
                    "$setOnInsert": {"firstSeenAt": now.datetime},
                },
                upsert=True,
            )


class ProviderException(Exception):
    pass


class UsageLimitException(ProviderException):
    pass
