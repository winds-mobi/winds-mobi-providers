import arrow
import arrow.parser
import requests

from commons.provider import Provider, ProviderException, Status, Q_, ureg, Pressure


class Holfuy(Provider):
    provider_code = 'holfuy'
    provider_name = 'holfuy.com'
    provider_urls = {
        'default': 'https://holfuy.com/en/weather/{id}',
        'en': 'https://holfuy.com/en/weather/{id}',
        'de': 'https://holfuy.com/de/weather/{id}',
        'fr': 'https://holfuy.com/fr/weather/{id}',
        'it': 'https://holfuy.com/it/weather/{id}'
    }

    def process_data(self):
        try:
            self.log.info('Processing Holfuy data...')
            holfuy_stations = requests.get('http://api.holfuy.com/stations/stations.json',
                                           timeout=(self.connect_timeout, self.read_timeout)).json()
            holfuy_data = requests.get('http://api.holfuy.com/live/?s=all&m=JSON&tu=C&su=km/h&utc',
                                       timeout=(self.connect_timeout, self.read_timeout)).json()
            holfuy_measures = {}
            for holfuy_measure in holfuy_data['measurements']:
                holfuy_measures[holfuy_measure['stationId']] = holfuy_measure

            for holfuy_station in holfuy_stations['holfuyStationsList']:
                holfuy_id = None
                station_id = None
                try:
                    holfuy_id = holfuy_station['id']
                    name = holfuy_station['name']
                    location = holfuy_station['location']
                    latitude = location.get('latitude')
                    longitude = location.get('longitude')
                    if (latitude is None or longitude is None) or (latitude == 0 and longitude == 0):
                        raise ProviderException('No geolocation found')
                    altitude = location.get('altitude')

                    urls = {lang: url.format(id=holfuy_id) for lang, url in self.provider_urls.items()}
                    station = self.save_station(
                        holfuy_id,
                        name,
                        name,
                        latitude,
                        longitude,
                        Status.GREEN,
                        altitude=altitude,
                        url=urls)
                    station_id = station['_id']

                    measures_collection = self.measures_collection(station_id)
                    new_measures = []

                    if holfuy_id not in holfuy_measures:
                        raise ProviderException("Station not found in 'api.holfuy.com/live/'")
                    holfuy_measure = holfuy_measures[holfuy_id]
                    last_measure_date = arrow.get(holfuy_measure['dateTime'])
                    key = last_measure_date.timestamp
                    if not self.has_measure(measures_collection, key):
                        measure = self.create_measure(
                            station,
                            key,
                            holfuy_measure['wind']['direction'],
                            Q_(holfuy_measure['wind']['speed'], ureg.kilometer / ureg.hour),
                            Q_(holfuy_measure['wind']['gust'], ureg.kilometer / ureg.hour),
                            temperature=Q_(
                                holfuy_measure['temperature'], ureg.degC) if 'temperature' in holfuy_measure else None,
                            pressure=Pressure(
                                qfe=None,
                                qnh=Q_(holfuy_measure['pressure'], ureg.hPa) if 'pressure' in holfuy_measure else None,
                                qff=None)
                        )
                        new_measures.append(measure)

                    self.insert_new_measures(measures_collection, station, new_measures)

                except ProviderException as e:
                    self.log.warn(f"Error while processing station '{station_id or holfuy_id}': {e}")
                except Exception as e:
                    self.log.exception(f"Error while processing station '{station_id or holfuy_id}': {e}")

        except Exception as e:
            self.log.exception(f'Error while processing Holfuy: {e}')

        self.log.info('Done !')


Holfuy().process_data()
