import urllib.parse

import arrow
import requests
from arrow.parser import ParserError

from commons.provider import Provider, Status, ProviderException, Pressure


class Pioupiou(Provider):
    provider_code = 'pioupiou'
    provider_name = 'pioupiou.com'
    provider_url = 'https://pioupiou.com'

    def get_status(self, station_id, status, location_date, location_status):
        if status == 'on':
            if location_date:
                if (arrow.utcnow().timestamp - location_date.timestamp) < 3600 * 24 * 15:
                    up_to_date = True
                else:
                    self.log.warn(f"'{station_id}': last known location date is {location_date.humanize()}")
                    up_to_date = False
            else:
                self.log.warn(f"'{station_id}': no last known location")
                return Status.RED

            if location_status and up_to_date:
                return Status.GREEN
            else:
                return Status.ORANGE
        else:
            return Status.HIDDEN

    def process_data(self):
        try:
            self.log.info('Processing Pioupiou data...')
            result = requests.get('http://api.pioupiou.fr/v1/live-with-meta/all', timeout=(self.connect_timeout,
                                                                                           self.read_timeout))
            station_id = None
            for piou_station in result.json()['data']:
                try:
                    piou_id = piou_station['id']
                    location = piou_station['location']
                    latitude = location.get('latitude')
                    longitude = location.get('longitude')
                    if (latitude is None or longitude is None) or (latitude == 0 and longitude == 0):
                        continue

                    location_date = None
                    if location['date']:
                        try:
                            location_date = arrow.get(location['date'])
                        except ParserError:
                            pass

                    station = self.save_station(
                        piou_id,
                        None,
                        None,
                        latitude,
                        longitude,
                        self.get_status(station_id, piou_station['status']['state'], location_date,
                                        location['success']),
                        url=urllib.parse.urljoin(self.provider_url, str(piou_id)),
                        default_name=piou_station.get('meta', {}).get('name', None))
                    station_id = station['_id']

                    measures_collection = self.measures_collection(station_id)
                    new_measures = []

                    piou_measure = piou_station['measurements']
                    last_measure_date = arrow.get(piou_measure['date'])
                    key = last_measure_date.timestamp
                    if not self.has_measure(measures_collection, key):
                        measure = self.create_measure(
                            station,
                            key,
                            piou_measure['wind_heading'],
                            piou_measure['wind_speed_avg'],
                            piou_measure['wind_speed_max'],
                            pressure=Pressure(qfe=piou_measure['pressure'], qnh=None, qff=None)
                        )
                        new_measures.append(measure)

                    self.insert_new_measures(measures_collection, station, new_measures)

                except ProviderException as e:
                    self.log.warn(f"Error while processing station '{station_id}': {e}")
                except Exception as e:
                    self.log.exception(f"Error while processing station '{station_id}': {e}")

        except Exception as e:
            self.log.exception(f'Error while processing Pioupiou: {e}')

        self.log.info('Done !')


Pioupiou().process_data()
