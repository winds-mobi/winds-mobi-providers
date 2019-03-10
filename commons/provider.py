import logging
import logging.config
import logging.handlers
import math
from collections import namedtuple
from os import path
from random import randint

import arrow
import dateutil
import redis
import requests
import sentry_sdk
import yaml
from pint import UnitRegistry
from pymongo import MongoClient, GEOSPHERE, ASCENDING

from commons.uwxutils import TWxUtils
from settings import LOG_DIR, MONGODB_URL, REDIS_URL, GOOGLE_API_KEY, SENTRY_URL

ureg = UnitRegistry()
Q_ = ureg.Quantity
Pressure = namedtuple('Pressure', ['qfe', 'qnh', 'qff'])


def get_logger(name):
    if LOG_DIR:
        with open(path.join(path.dirname(path.abspath(__file__)), 'logging_file.yml')) as f:
            dict = yaml.load(f)
            dict['handlers']['file']['filename'] = path.join(path.expanduser(LOG_DIR), f'{name}.log')
            logging.config.dictConfig(dict)
    else:
        with open(path.join(path.dirname(path.abspath(__file__)), 'logging_console.yml')) as f:
            logging.config.dictConfig(yaml.load(f))
    return logging.getLogger(name)


class ProviderException(Exception):
    pass


class UsageLimitException(ProviderException):
    pass


class Status:
    HIDDEN = 'hidden'
    RED = 'red'
    ORANGE = 'orange'
    GREEN = 'green'


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
    return str(value).lower() in ['true', 'yes']


class Provider:
    provider_code = ''
    provider_name = ''
    provider_url = ''

    connect_timeout = 7
    read_timeout = 30

    @property
    def usage_limit_cache_duration(self):
        return (12 + randint(-2, 2)) * 3600

    @property
    def location_cache_duration(self):
        return (60 + randint(-2, 2)) * 24 * 3600

    def __init__(self):
        self.mongo_db = MongoClient(MONGODB_URL).get_database()
        self.__stations_collection = self.mongo_db.stations
        self.__stations_collection.create_index([('loc', GEOSPHERE), ('status', ASCENDING), ('pv-code', ASCENDING),
                                                 ('short', ASCENDING), ('name', ASCENDING)])
        self.collection_names = self.mongo_db.collection_names()
        self.redis = redis.StrictRedis.from_url(url=REDIS_URL, decode_responses=True)
        self.google_api_key = GOOGLE_API_KEY
        self.log = get_logger(self.provider_code)
        sentry_sdk.init(SENTRY_URL)
        with sentry_sdk.configure_scope() as scope:
            scope.set_tag('provider', self.provider_name)

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
            qff = TWxUtils.StationToSeaLevelPressure(qfe, elevationM=altitude, currentTempC=temperature,
                                                     meanTempC=temperature, humidity=humidity)
        if qff and qfe is None and temperature is not None and humidity is not None:
            qfe = TWxUtils.SeaLevelToStationPressure(qff, elevationM=altitude, currentTempC=temperature,
                                                     meanTempC=temperature, humidity=humidity)

        return {
            'qfe': to_float(qfe),
            'qnh': to_float(qnh),
            'qff': to_float(qff)
        }

    def __to_altitude(self, value):
        if isinstance(value, ureg.Quantity):
            return to_int(value.to(ureg.meter).magnitude)
        else:
            return to_int(value)

    def __to_rain(self, value):
        if isinstance(value, ureg.Quantity):
            return to_float(value.to(ureg.liter / (ureg.meter ** 2)).magnitude, 1)
        else:
            return to_float(value, 1)

    def stations_collection(self):
        return self.__stations_collection

    def measures_collection(self, station_id):
        if station_id not in self.collection_names:
            self.mongo_db.create_collection(station_id, **{'capped': True, 'size': 500000, 'max': 5000})
            self.collection_names.append(station_id)
        return self.mongo_db[station_id]

    def add_redis_key(self, key, values, cache_duration):
        pipe = self.redis.pipeline()
        pipe.hmset(key, values)
        pipe.expire(key, cache_duration)
        pipe.execute()

    def __compute_elevation(self, lat, lon):
        radius = 500
        nb = 6
        path = f'{lat},{lon}|'
        for k in range(nb):
            angle = math.pi * 2 * k / nb
            dx = radius * math.cos(angle)
            dy = radius * math.sin(angle)
            path += '{lat},{lon}'.format(
                lat=str(lat + (180 / math.pi) * (dy / 6378137)),
                lon=str(lon + (180 / math.pi) * (dx / 6378137) / math.cos(lat * math.pi / 180)))
            if k < nb - 1:
                path += '|'

        result = requests.get(
            f'https://maps.googleapis.com/maps/api/elevation/json?locations={path}&key={self.google_api_key}',
            timeout=(self.connect_timeout, self.read_timeout)).json()
        if result['status'] == 'OVER_QUERY_LIMIT':
            raise UsageLimitException('Google Elevation API OVER_QUERY_LIMIT')
        elif result['status'] == 'INVALID_REQUEST':
            raise ProviderException(f'Google Elevation API INVALID_REQUEST: {result.get("error_message", "")}')
        elif result['status'] == 'ZERO_RESULTS':
            raise ProviderException('Google Elevation API ZERO_RESULTS')

        elevation = float(result['results'][0]['elevation'])
        is_peak = False
        for point in result['results'][1:]:
            try:
                glide_ratio = radius / (elevation - float(point['elevation']))
            except ZeroDivisionError:
                glide_ratio = float('Infinity')
            if 0 < glide_ratio < 6:
                is_peak = True
                break
        return elevation, is_peak

    def __get_place_geocoding_results(self, results):
        lat, lon, address_long_name = None, None, None

        for result in results['results']:
            if result.get('geometry', {}).get('location'):
                lat = result['geometry']['location']['lat']
                lon = result['geometry']['location']['lng']
                for component in result['address_components']:
                    if 'postal_code' not in component['types']:
                        address_long_name = component['long_name']
                        break
                break
        return lat, lon, address_long_name

    def __get_place_autocomplete(self, name):
        results = requests.get(
            f'https://maps.googleapis.com/maps/api/place/autocomplete/json?input={name}&key={self.google_api_key}',
            timeout=(self.connect_timeout, self.read_timeout)).json()

        if results['status'] == 'OVER_QUERY_LIMIT':
            raise UsageLimitException('Google Places API OVER_QUERY_LIMIT')
        elif results['status'] == 'INVALID_REQUEST':
            raise ProviderException(f'Google Places API INVALID_REQUEST: {results.get("error_message", "")}')
        elif results['status'] == 'ZERO_RESULTS':
            raise ProviderException(f"Google Places API ZERO_RESULTS for '{name}'")

        place_id = results['predictions'][0]['place_id']

        results = requests.get(
            f'https://maps.googleapis.com/maps/api/geocode/json?place_id={place_id}&key={self.google_api_key}',
            timeout=(self.connect_timeout, self.read_timeout)).json()

        if results['status'] == 'OVER_QUERY_LIMIT':
            raise UsageLimitException('Google Geocoding API OVER_QUERY_LIMIT')
        elif results['status'] == 'INVALID_REQUEST':
            raise ProviderException(f'Google Geocoding API INVALID_REQUEST: {results.get("error_message", "")}')
        elif results['status'] == 'ZERO_RESULTS':
            raise ProviderException(f"Google Geocoding API ZERO_RESULTS for '{name}'")

        return self.__get_place_geocoding_results(results)

    def __get_place_geocoding(self, name):
        results = requests.get(
            f'https://maps.googleapis.com/maps/api/geocode/json?address={name}&key={self.google_api_key}',
            timeout=(self.connect_timeout, self.read_timeout)).json()
        if results['status'] == 'OVER_QUERY_LIMIT':
            raise UsageLimitException('Google Geocoding API OVER_QUERY_LIMIT')
        elif results['status'] == 'INVALID_REQUEST':
            raise ProviderException(f'Google Geocoding API INVALID_REQUEST: {results.get("error_message", "")}')
        elif results['status'] == 'ZERO_RESULTS':
            raise ProviderException(f"Google Geocoding API ZERO_RESULTS for '{name}'")

        return self.__get_place_geocoding_results(results)

    def get_station_id(self, provider_id):
        return self.provider_code + '-' + str(provider_id)

    def __create_station(self, provider_id, short_name, name, latitude, longitude, altitude, is_peak, status, tz, urls,
                         fixes=None):
        if fixes is None:
            fixes = {}

        if any((not short_name, not name, altitude is None, latitude is None, longitude is None, not status, not tz)):
            raise ProviderException('A mandatory value is none!')

        station = {
            'pv-id': provider_id,
            'pv-code': self.provider_code,
            'pv-name': self.provider_name,
            'url': urls,
            'short': fixes.get('short') or short_name,
            'name': fixes.get('name') or name,
            'alt': self.__to_altitude(fixes['alt'] if 'alt' in fixes else altitude),
            'peak': to_bool(fixes['peak'] if 'peak' in fixes else is_peak),
            'loc': {
                'type': 'Point',
                'coordinates': [
                    to_float(fixes['longitude'] if 'longitude' in fixes else longitude, 6),
                    to_float(fixes['latitude'] if 'latitude' in fixes else latitude, 6)
                ]
            },
            'status': status,
            'tz': tz,
            'seen': arrow.utcnow().timestamp
        }
        return station

    def save_station(self, provider_id, short_name, name, latitude, longitude, status, altitude=None, tz=None, url=None,
                     default_name=None, lookup_name=None):

        if provider_id is None:
            raise ProviderException("'provider id' is none!")
        station_id = self.get_station_id(provider_id)
        lat = to_float(latitude, 6)
        lon = to_float(longitude, 6)

        address_key = f'address/{lat},{lon}'
        if (not short_name or not name) and not self.redis.exists(address_key):
            try:
                results = requests.get(
                    f'https://maps.googleapis.com/maps/api/geocode/json?latlng={lat},{lon}'
                    f'&result_type=airport|colloquial_area|locality|natural_feature|point_of_interest|neighborhood'
                    f'&key={self.google_api_key}',
                    timeout=(self.connect_timeout, self.read_timeout)).json()

                if results['status'] == 'OVER_QUERY_LIMIT':
                    raise UsageLimitException('Google Geocoding API OVER_QUERY_LIMIT')
                elif results['status'] == 'INVALID_REQUEST':
                    raise ProviderException(f'Google Geocoding API INVALID_REQUEST: {results.get("error_message", "")}')
                elif results['status'] == 'ZERO_RESULTS':
                    raise ProviderException('Google Geocoding API ZERO_RESULTS')

                address_short_name = None
                address_long_name = None
                for result in results['results']:
                    for component in result['address_components']:
                        if 'postal_code' not in component['types']:
                            address_short_name = component['short_name']
                            address_long_name = component['long_name']
                            break
                if not address_short_name or not address_long_name:
                    raise ProviderException('Google Geocoding API: No valid address name found')
                self.add_redis_key(address_key, {
                    'short': address_short_name,
                    'name': address_long_name
                }, self.location_cache_duration)
            except TimeoutError as e:
                raise e
            except UsageLimitException as e:
                self.add_redis_key(address_key, {
                    'error': repr(e)
                }, self.usage_limit_cache_duration)
            except Exception as e:
                if not isinstance(e, ProviderException):
                    self.log.exception('Unable to call Google Geocoding API')
                self.add_redis_key(address_key, {
                    'error': repr(e)
                }, self.location_cache_duration)

        address = lookup_name or name or short_name
        geolocation_key = f'geolocation/{address}'
        if (lat is None or lon is None) or (lat == 0 and lon == 0):
            if not self.redis.exists(geolocation_key):
                try:
                    lat, lon, address_long_name = self.__get_place_geocoding(address)
                    if not lat or not lon or not address_long_name:
                        raise ProviderException(f'Google Geocoding API: No valid geolocation found {address}')
                    self.add_redis_key(geolocation_key, {
                        'lat': lat,
                        'lon': lon,
                        'name': address_long_name
                    }, self.location_cache_duration)
                except TimeoutError as e:
                    raise e
                except UsageLimitException as e:
                    self.add_redis_key(geolocation_key, {
                        'error': repr(e)
                    }, self.usage_limit_cache_duration)
                except Exception as e:
                    if not isinstance(e, ProviderException):
                        self.log.exception('Unable to call Google Geocoding API')
                    self.add_redis_key(geolocation_key, {
                        'error': repr(e)
                    }, self.location_cache_duration)
            if self.redis.exists(geolocation_key):
                if self.redis.hexists(geolocation_key, 'error'):
                    raise ProviderException(
                        f'Unable to determine station geolocation: {self.redis.hget(geolocation_key, "error")}')
                lat = to_float(self.redis.hget(geolocation_key, 'lat'), 6)
                lon = to_float(self.redis.hget(geolocation_key, 'lon'), 6)
                if not name:
                    name = self.redis.hget(geolocation_key, 'name')

        alt_key = f'alt/{lat},{lon}'
        if not self.redis.exists(alt_key):
            try:
                elevation, is_peak = self.__compute_elevation(lat, lon)
                self.add_redis_key(alt_key, {
                    'alt': elevation,
                    'is_peak': is_peak
                }, self.location_cache_duration)
            except TimeoutError as e:
                raise e
            except UsageLimitException as e:
                self.add_redis_key(alt_key, {
                    'error': repr(e)
                }, self.usage_limit_cache_duration)
            except Exception as e:
                if not isinstance(e, ProviderException):
                    self.log.exception('Unable to call Google Elevation API')
                self.add_redis_key(alt_key, {
                    'error': repr(e)
                }, self.location_cache_duration)

        tz_key = f'tz/{lat},{lon}'
        if not tz and not self.redis.exists(tz_key):
            try:
                now = arrow.utcnow().timestamp
                result = requests.get(
                    f'https://maps.googleapis.com/maps/api/timezone/json?location={lat},{lon}'
                    f'&timestamp={now}&key={self.google_api_key}',
                    timeout=(self.connect_timeout, self.read_timeout)).json()

                if result['status'] == 'OVER_QUERY_LIMIT':
                    raise UsageLimitException('Google Time Zone API OVER_QUERY_LIMIT')
                elif result['status'] == 'INVALID_REQUEST':
                    raise ProviderException(f'Google Time Zone API INVALID_REQUEST: {result.get("error_message", "")}')
                elif result['status'] == 'ZERO_RESULTS':
                    raise ProviderException('Google Time Zone API ZERO_RESULTS')

                tz = result['timeZoneId']
                dateutil.tz.gettz(tz)
                self.add_redis_key(tz_key, {
                    'tz': tz
                }, self.location_cache_duration)
            except TimeoutError as e:
                raise e
            except UsageLimitException as e:
                self.add_redis_key(tz_key, {
                    'error': repr(e)
                }, self.usage_limit_cache_duration)
            except Exception as e:
                if not isinstance(e, ProviderException):
                    self.log.exception('Unable to call Google Time Zone API')
                self.add_redis_key(tz_key, {
                    'error': repr(e)
                }, self.location_cache_duration)

        if not short_name:
            if self.redis.hexists(address_key, 'error'):
                if default_name:
                    short_name = default_name
                else:
                    raise ProviderException(
                        f"Unable to determine station 'short': {self.redis.hget(address_key, 'error')}")
            else:
                short_name = self.redis.hget(address_key, 'short')

        if not name:
            if self.redis.hexists(address_key, 'error'):
                if default_name:
                    name = default_name
                else:
                    raise ProviderException(
                        f"Unable to determine station 'name': {self.redis.hget(address_key, 'error')}")
            else:
                name = self.redis.hget(address_key, 'name')

        if not altitude:
            if self.redis.hexists(alt_key, 'error'):
                raise ProviderException(f"Unable to determine station 'alt': {self.redis.hget(alt_key, 'error')}")
            altitude = self.redis.hget(alt_key, 'alt')

        if self.redis.hexists(alt_key, 'error') == 'error':
            raise ProviderException(f"Unable to determine station 'peak': {self.redis.hget(alt_key, 'error')}")
        is_peak = self.redis.hget(alt_key, 'is_peak')

        if not tz:
            if self.redis.hexists(tz_key, 'error'):
                raise ProviderException(f"Unable to determine station 'tz': {self.redis.hget(tz_key, 'error')}")
            tz = self.redis.hget(tz_key, 'tz')

        if not url:
            urls = {
                'default': self.provider_url
            }
        elif isinstance(url, str):
            urls = {
                'default': url
            }
        elif isinstance(url, dict):
            if 'default' not in url:
                raise ProviderException("No 'default' key in url")
            urls = url
        else:
            raise ProviderException('Invalid url')

        fixes = self.mongo_db.stations_fix.find_one(station_id)
        station = self.__create_station(provider_id, short_name, name, lat, lon, altitude, is_peak, status, tz, urls,
                                        fixes)
        self.stations_collection().update({'_id': station_id}, {'$set': station}, upsert=True)
        station['_id'] = station_id
        return station

    def create_measure(self, for_station, _id, wind_direction, wind_average, wind_maximum,
                       temperature=None, humidity=None, pressure: Pressure = None, rain=None):

        if all((wind_direction is None, wind_average is None, wind_maximum is None)):
            raise ProviderException('All mandatory values are null!')

        # Mandatory keys: json 'null' if not present
        measure = {
            '_id': int(round(_id)),
            'w-dir': self.__to_wind_direction(wind_direction),
            'w-avg': self.__to_wind_speed(wind_average),
            'w-max': self.__to_wind_speed(wind_maximum)
        }

        # Optional keys
        if temperature is not None:
            measure['temp'] = self.__to_temperature(temperature)
        if humidity is not None:
            measure['hum'] = to_float(humidity, 1)
        if pressure is not None and (pressure.qfe is not None or pressure.qnh is not None or pressure.qff is not None):
            measure['pres'] = self.__compute_pressures(pressure, for_station['alt'], measure.get('temp', None),
                                                       measure.get('hum', None))
        if rain is not None:
            measure['rain'] = self.__to_rain(rain)

        measure['time'] = arrow.now().timestamp
        return measure

    def has_measure(self, measure_collection, key):
        return measure_collection.find({'_id': key}).count() > 0

    def insert_new_measures(self, measure_collection, station, new_measures):
        if len(new_measures) > 0:
            measure_collection.insert(sorted(new_measures, key=lambda m: m['_id']))

            end_date = arrow.Arrow.fromtimestamp(new_measures[-1]['_id'], dateutil.tz.gettz(station['tz']))
            self.log.info(
                '--> {end_date} ({end_date_local}), {short}/{name} ({id}): {nb} values inserted'.format(
                    end_date=end_date.format('YY-MM-DD HH:mm:ssZZ'),
                    end_date_local=end_date.to('local').format('YY-MM-DD HH:mm:ssZZ'),
                    short=station['short'],
                    name=station['name'],
                    id=station['_id'],
                    nb=str(len(new_measures))))

            self.__add_last_measure(measure_collection, station['_id'])

    def __add_last_measure(self, measure_collection, station_id):
        last_measure = measure_collection.find_one({'$query': {}, '$orderby': {'_id': -1}})
        if last_measure:
            self.stations_collection().update({'_id': station_id}, {'$set': {'last': last_measure}})
