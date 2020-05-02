import arrow
import arrow.parser
import requests
import urllib3

from winds_mobi_providers.provider import Provider, ProviderException, StationStatus

# Disable urllib3 warning because https://www.windspots.com has a certificates chain issue
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class Windspots(Provider):
    provider_code = 'windspots'
    provider_name = 'windspots.com'
    provider_url = 'https://www.windspots.com'

    def process_data(self):
        try:
            self.log.info('Processing WindsSpots data...')
            result = requests.get('https://api.windspots.com/windmobile/stationinfos?allStation=true',
                                  timeout=(self.connect_timeout, self.read_timeout), verify=False)

            for windspots_station in result.json()['stationInfo']:
                station_id = None
                try:
                    windspots_id = windspots_station['@id'][10:]
                    station = self.save_station(
                        windspots_id,
                        windspots_station['@shortName'],
                        windspots_station['@name'],
                        windspots_station['@wgs84Latitude'],
                        windspots_station['@wgs84Longitude'],
                        StationStatus(windspots_station['@maintenanceStatus']),
                        altitude=windspots_station['@altitude'])
                    station_id = station['_id']

                    try:
                        # Asking 2 days of data
                        result = requests.get(
                            f'https://api.windspots.com/windmobile/stationdatas/windspots:{windspots_id}',
                            timeout=(self.connect_timeout, self.read_timeout), verify=False)
                        try:
                            windspots_measure = result.json()
                        except ValueError:
                            raise ProviderException('Action=Data return invalid json response')

                        measures_collection = self.measures_collection(station_id)

                        new_measures = []
                        try:
                            key = arrow.get(windspots_measure['@lastUpdate'], 'YYYY-M-DTHH:mm:ssZZ').timestamp
                        except arrow.parser.ParserError:
                            raise ProviderException(
                                f"Unable to parse measure date: '{windspots_measure['@lastUpdate']}")

                        wind_direction_last = windspots_measure['windDirectionChart']['serie']['points'][0]
                        wind_direction_key = int(wind_direction_last['date']) // 1000
                        if arrow.get(key).minute != arrow.get(wind_direction_key).minute:
                            key_time = arrow.get(key).to('local').format('YY-MM-DD HH:mm:ssZZ')
                            direction_time = arrow.get(wind_direction_key).to('local').format('YY-MM-DD HH:mm:ssZZ')
                            self.log.warning(
                                f"{station['short']} ({station_id}): wind direction time '{direction_time}' is "
                                f"inconsistent with measure time '{key_time}'"
                            )

                        if not self.has_measure(measures_collection, key):
                            try:
                                measure = self.create_measure(
                                    station,
                                    key,
                                    wind_direction_last['value'],
                                    windspots_measure.get('windAverage'),
                                    windspots_measure.get('windMax'),
                                    temperature=windspots_measure.get('airTemperature'),
                                    humidity=windspots_measure.get('airHumidity'),
                                )
                                new_measures.append(measure)
                            except ProviderException as e:
                                self.log.warning(
                                    f"Error while processing measure '{key}' for station '{station_id}': {e}")
                            except Exception as e:
                                self.log.exception(
                                    f"Error while processing measure '{key}' for station '{station_id}': {e}")

                        self.insert_new_measures(measures_collection, station, new_measures)

                    except Exception as e:
                        self.log.exception(f"Error while processing measure for station '{station_id}': {e}")
                except Exception as e:
                    self.log.exception(f"Error while processing station '{station_id}': {e}")
        except Exception as e:
            self.log.exception(f'Error while processing Windspots: {e}')

        self.log.info('Done !')


if __name__ == '__main__':
    Windspots().process_data()
