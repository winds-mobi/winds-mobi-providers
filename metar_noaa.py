import json
import math
import os
import warnings
from random import randint

import arrow
import arrow.parser
import requests
from metar.Metar import Metar

from commons.provider import Provider, ProviderException, Status, ureg, Q_, UsageLimitException, Pressure
from settings import CHECKWX_API_KEY


class MetarNoaa(Provider):
    provider_code = 'metar'
    provider_name = 'noaa.gov/metar'
    provider_url = 'http://aviationweather.cp.ncep.noaa.gov/metar/'

    def __init__(self):
        super().__init__()
        self.checkwx_api_key = CHECKWX_API_KEY

    @property
    def checkwx_cache_duration(self):
        return (20 + randint(-2, 2)) * 24 * 3600

    direction_units = {
        'degree': ureg.degree,
    }

    speed_units = {
        'KT': ureg.knot,
        'MPS': ureg.meter / ureg.second,
        'KMH': ureg.kilometer / ureg.hour,
        'MPH': ureg.mile / ureg.hour
    }

    temperature_units = {
        'F': ureg.degF,
        'C': ureg.degC,
        'K': ureg.degK
    }

    pressure_units = {
        'MB': ureg.hPa,
        'HPA': ureg.hPa,
        'IN': ureg.in_Hg
    }

    def get_quantity(self, measure, units):
        if measure:
            return Q_(measure._value, units[measure._units])

    def get_direction(self, measure):
        if measure:
            return Q_(measure._degrees, self.direction_units['degree'])
        else:
            # For VaRiaBle direction, use a random value
            return Q_(randint(0, 359), self.direction_units['degree'])

    def compute_humidity(self, dew_point, temp):
        if not (dew_point and temp):
            return None

        a = 17.625
        b = 243.04
        td = dew_point.to(ureg.degC).magnitude
        t = temp.to(ureg.degC).magnitude

        return 100 * (math.exp((a * td) / (b + td))) / (math.exp((a * t) / (b + t)))

    def process_data(self):
        try:
            self.log.info('Processing Metar data...')

            with open(os.path.join(os.path.dirname(__file__), 'metar/stations.json')) as in_file:
                icao = json.load(in_file)

            now = arrow.utcnow()
            hour = now.hour
            minute = now.minute

            if minute < 45:
                current_cycle = hour
            else:
                current_cycle = hour + 1 % 24

            stations = {}
            for cycle in (current_cycle-1, current_cycle):
                file = f'http://tgftp.nws.noaa.gov/data/observations/metar/cycles/{cycle:02d}Z.TXT'
                self.log.info(f"Processing '{file}' ...")

                request = requests.get(file, stream=True, timeout=(self.connect_timeout, self.read_timeout))
                for line in request.iter_lines():
                    if line:
                        data = line.decode('iso-8859-1')
                        try:
                            # Is this line a date with format "2017/05/12 23:55" ?
                            arrow.get(data, 'YYYY/MM/DD HH:mm')
                            continue
                            # Catch also ValueError because https://github.com/crsmithdev/arrow/issues/535
                        except (arrow.parser.ParserError, ValueError):
                            try:
                                metar = Metar(data, strict=False)
                                # wind_dir could be NONE if 'dir' is 'VRB'
                                if metar.wind_speed:
                                    if metar.station_id not in stations:
                                        stations[metar.station_id] = {}
                                    key = arrow.get(metar.time).timestamp
                                    stations[metar.station_id][key] = metar
                            except Exception as e:
                                self.log.warn(f'Error while parsing METAR data: {e}')
                                continue

            for metar_id in stations:
                metar = next(iter(stations[metar_id].values()))
                try:
                    name, short_name, default_name, lat, lon, altitude, tz = None, None, None, None, None, None, None

                    checkwx_key = f'metar/checkwx/{metar.station_id}'
                    if not self.redis.exists(checkwx_key):
                        try:
                            self.log.info('Calling api.checkwx.com...')
                            request = requests.get(
                                f'https://api.checkwx.com/station/{metar.station_id}',
                                headers={'Accept': 'application/json', 'X-API-Key': self.checkwx_api_key},
                                timeout=(self.connect_timeout, self.read_timeout)
                            )
                            if request.status_code == 401:
                                raise UsageLimitException(request.json()['errors'][0]['message'])
                            elif request.status_code == 429:
                                raise UsageLimitException('api.checkwx.com rate limit exceeded')

                            try:
                                checkwx_data = request.json()['data'][0]
                                if 'icao' not in checkwx_data:
                                    raise ProviderException('Invalid CheckWX data')
                            except (ValueError, KeyError):
                                checkwx_json = request.json()
                                messages = []
                                if type(checkwx_json['data']) is list:
                                    messages.extend(checkwx_json['data'])
                                else:
                                    messages.append(checkwx_json['data'])
                                raise ProviderException(f'CheckWX API error: {",".join(messages)}')

                            self.add_redis_key(checkwx_key, {
                                'data': json.dumps(checkwx_data),
                                'date': arrow.now().format('YYYY-MM-DD HH:mm:ssZZ'),
                            }, self.checkwx_cache_duration)
                        except TimeoutError as e:
                            raise e
                        except UsageLimitException as e:
                            self.add_redis_key(checkwx_key, {
                                'error': repr(e),
                                'date': arrow.now().format('YYYY-MM-DD HH:mm:ssZZ'),
                            }, self.usage_limit_cache_duration)
                        except Exception as e:
                            if not isinstance(e, ProviderException):
                                self.log.exception('Error while getting CheckWX data')
                            else:
                                self.log.warn(f'Error while getting CheckWX data: {e}')
                            self.add_redis_key(checkwx_key, {
                                'error': repr(e),
                                'date': arrow.now().format('YYYY-MM-DD HH:mm:ssZZ'),
                            }, self.checkwx_cache_duration)

                    if not self.redis.hexists(checkwx_key, 'error'):
                        checkwx_data = json.loads(self.redis.hget(checkwx_key, 'data'))

                        station_type = checkwx_data.get('type', None)
                        if station_type:
                            name = f'{checkwx_data["name"]} {station_type}'
                        else:
                            name = checkwx_data['name']
                        city = checkwx_data.get('city', None)
                        if city:
                            if station_type:
                                short_name = f'{city} {station_type}'
                            else:
                                short_name = city
                        else:
                            default_name = checkwx_data['name']

                        lat = checkwx_data['latitude']['decimal']
                        lon = checkwx_data['longitude']['decimal']
                        tz = checkwx_data['timezone']['tzid']
                        elevation = checkwx_data.get('elevation', None)
                        altitude = None
                        if elevation:
                            if 'meters' in elevation:
                                altitude = Q_(elevation['meters'], ureg.meters)
                            elif 'feet' in elevation:
                                altitude = Q_(elevation['feet'], ureg.feet)

                    if metar.station_id in icao:
                        lat = lat or icao[metar.station_id]['lat']
                        lon = lon or icao[metar.station_id]['lon']
                        default_name = default_name or icao[metar.station_id]['name']

                    station = self.save_station(
                        metar.station_id,
                        short_name,
                        name,
                        lat,
                        lon,
                        Status.GREEN,
                        altitude=altitude,
                        tz=tz,
                        url=os.path.join(self.provider_url, f'site?id={metar.station_id}&db=metar'),
                        default_name=default_name or f'{metar.station_id} Airport',
                        lookup_name=f'{metar.station_id} Airport ICAO')
                    station_id = station['_id']

                    if metar.station_id not in icao:
                        self.log.warn(f"Missing '{metar.station_id}' ICAO in database. Is it '{station['name']}'?")

                    measures_collection = self.measures_collection(station_id)
                    new_measures = []
                    for key in stations[metar_id]:
                        metar = stations[metar_id][key]
                        if not self.has_measure(measures_collection, key):
                            temp = self.get_quantity(metar.temp, self.temperature_units)
                            dew_point = self.get_quantity(metar.dewpt, self.temperature_units)
                            humidity = self.compute_humidity(dew_point, temp)
                            measure = self.create_measure(
                                station,
                                key,
                                self.get_direction(metar.wind_dir),
                                self.get_quantity(metar.wind_speed, self.speed_units),
                                self.get_quantity(metar.wind_gust or metar.wind_speed, self.speed_units),
                                temperature=temp,
                                humidity=humidity,
                                pressure=Pressure(qfe=None,
                                                  qnh=self.get_quantity(metar.press, self.pressure_units),
                                                  qff=self.get_quantity(metar.press_sea_level, self.pressure_units))
                            )
                            new_measures.append(measure)

                    self.insert_new_measures(measures_collection, station, new_measures)

                except ProviderException as e:
                    self.log.warn(f"Error while processing station '{metar_id}': {e}")
                except Exception as e:
                    self.log.exception(f"Error while processing station '{metar_id}': {e}")

        except Exception as e:
            self.log.exception(f'Error while processing Metar: {e}')

        self.log.info('Done !')


with warnings.catch_warnings():
    warnings.simplefilter('ignore')
    MetarNoaa().process_data()
