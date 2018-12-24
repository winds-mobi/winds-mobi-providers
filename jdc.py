import urllib.parse

import requests

from commons.provider import Provider, ProviderException, Status, Pressure


class Jdc(Provider):
    provider_code = 'jdc'
    provider_name = 'jdc.ch'
    provider_url = 'http://meteo.jdc.ch'

    # Jdc status: offline, maintenance, test or online
    def get_status(self, status):
        if status == 'offline':
            return Status.HIDDEN
        elif status == 'maintenance':
            return Status.RED
        elif status == 'test':
            return Status.ORANGE
        elif status == 'online':
            return Status.GREEN
        else:
            return Status.HIDDEN

    def process_data(self):
        try:
            self.log.info('Processing JDC data...')
            result = requests.get('http://meteo.jdc.ch/API/?Action=StationView&flags=all',
                                  timeout=(self.connect_timeout, self.read_timeout))

            try:
                jdc_stations = result.json()['Stations']
            except Exception:
                raise Exception('Action=StationView returns invalid json response')

            for jdc_station in jdc_stations:
                station_id = None
                try:
                    jdc_id = jdc_station['serial']
                    station = self.save_station(
                        jdc_id,
                        jdc_station['short-name'],
                        jdc_station['name'],
                        jdc_station['latitude'],
                        jdc_station['longitude'],
                        self.get_status(jdc_station['status']),
                        altitude=jdc_station['altitude'],
                        url=urllib.parse.urljoin(self.provider_url, '/station/' + str(jdc_station['serial'])))
                    station_id = station['_id']

                    try:
                        # Asking 2 days of data
                        result = requests.get(
                            f'http://meteo.jdc.ch/API/?Action=DataView&serial={jdc_id}&duration=172800',
                            timeout=(self.connect_timeout, self.read_timeout))
                        try:
                            json = result.json()
                        except ValueError:
                            raise Exception('Action=DataView returns invalid json response')
                        if json['ERROR'] == 'OK':
                            measures_collection = self.measures_collection(station_id)

                            measures = json['data']['measurements']
                            new_measures = []
                            for jdc_measure in measures:
                                key = jdc_measure['unix-time']
                                if not self.has_measure(measures_collection, key):
                                    try:
                                        measure = self.create_measure(
                                            station,
                                            key,
                                            jdc_measure.get('wind-direction'),
                                            jdc_measure.get('wind-average'),
                                            jdc_measure.get('wind-maximum'),
                                            temperature=jdc_measure.get('temperature'),
                                            humidity=jdc_measure.get('humidity'),
                                            pressure=Pressure(
                                                qfe=jdc_measure.get('pressure', None),
                                                qnh=None,
                                                qff=None),
                                            rain=jdc_measure.get('rain', None),
                                        )
                                        new_measures.append(measure)
                                    except ProviderException as e:
                                        self.log.warn(
                                            f"Error while processing measure '{key}' for station '{station_id}': {e}")
                                    except Exception as e:
                                        self.log.exception(
                                            f"Error while processing measure '{key}' for station '{station_id}': {e}")

                            self.insert_new_measures(measures_collection, station, new_measures)
                        else:
                            raise ProviderException(f"Action=Data returns an error: '{json['ERROR']}'")

                    except ProviderException as e:
                        self.log.warn(f"Error while processing measures for station '{station_id}': {e}")
                    except Exception as e:
                        self.log.exception(f"Error while processing measures for station '{station_id}': {e}")

                except ProviderException as e:
                    self.log.warn(f"Error while processing station '{station_id}': {e}")
                except Exception as e:
                    self.log.exception(f"Error while processing station '{station_id}': {e}")

        except Exception as e:
            self.log.exception(f'Error while processing JDC: {e}')

        self.log.info('Done !')


Jdc().process_data()
