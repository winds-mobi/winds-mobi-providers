import logging

import arrow
import requests
from dateutil import tz
from tenacity import retry, wait_random_exponential, stop_after_delay, after_log

from winds_mobi_providers import Provider, ProviderException, StationStatus, Pressure


class Ffvl(Provider):
    provider_code = 'ffvl'
    provider_name = 'ffvl.fr'
    provider_url = 'http://www.balisemeteo.com'

    def process_data(self):
        stations = {}
        try:
            self.log.info('Processing FFVL data...')

            result = requests.get(
                'http://data.ffvl.fr/json/balises.json', timeout=(self.connect_timeout, self.read_timeout))
            ffvl_stations = result.json()

            for ffvl_station in ffvl_stations:
                ffvl_id = None
                try:
                    type = ffvl_station.get('station_type', '').lower()
                    if type not in ['holfuy', 'pioupiou', 'iweathar']:
                        ffvl_id = ffvl_station['idBalise']
                        station = self.save_station(
                            ffvl_id,
                            ffvl_station['nom'],
                            ffvl_station['nom'],
                            ffvl_station['latitude'],
                            ffvl_station['longitude'],
                            StationStatus.GREEN,
                            altitude=ffvl_station['altitude'],
                            url=ffvl_station['url'])
                        stations[station['_id']] = station

                except ProviderException as e:
                    self.log.warning(f"Error while processing station '{ffvl_id}': {e}")
                except Exception as e:
                    self.log.exception(f"Error while processing station '{ffvl_id}': {e}")

        except ProviderException as e:
            self.log.warning(f'Error while processing stations: {e}')
        except Exception as e:
            self.log.exception(f'Error while processing stations: {e}')

        try:
            @retry(wait=wait_random_exponential(multiplier=2, min=2), stop=stop_after_delay(60),
                   after=after_log(self.log, logging.WARNING))
            def request_data():
                # data.ffvl.fr randomly returns an empty file instead the json doc
                result = requests.get(
                    'http://data.ffvl.fr/json/relevesmeteo.json', timeout=(self.connect_timeout, self.read_timeout))
                return result.json()

            ffvl_measures = request_data()

            ffvl_tz = tz.gettz('Europe/Paris')
            for ffvl_measure in ffvl_measures:
                station_id = None
                try:
                    ffvl_id = ffvl_measure['idbalise']
                    station_id = self.get_station_id(ffvl_id)
                    if station_id not in stations:
                        raise ProviderException(f"Unknown station '{station_id}'")
                    station = stations[station_id]

                    measures_collection = self.measures_collection(station_id)
                    key = arrow.get(ffvl_measure['date'], 'YYYY-MM-DD HH:mm:ss').replace(tzinfo=ffvl_tz).timestamp

                    if not self.has_measure(measures_collection, key):
                        measure = self.create_measure(
                            station,
                            key,
                            ffvl_measure['directVentMoy'],
                            ffvl_measure['vitesseVentMoy'],
                            ffvl_measure['vitesseVentMax'],
                            temperature=ffvl_measure['temperature'],
                            humidity=ffvl_measure['hydrometrie'],
                            pressure=Pressure(qfe=ffvl_measure['pression'], qnh=None, qff=None)
                        )
                        self.insert_new_measures(measures_collection, station, [measure])

                except ProviderException as e:
                    self.log.warning(f"Error while processing measures for station '{station_id}': {e}")
                except Exception as e:
                    self.log.exception(f"Error while processing measures for station '{station_id}': {e}")

        except ProviderException as e:
            self.log.warning(f'Error while processing FFVL: {e}')
        except Exception as e:
            self.log.exception(f'Error while processing FFVL: {e}')

        self.log.info('...Done!')


if __name__ == '__main__':
    Ffvl().process_data()
