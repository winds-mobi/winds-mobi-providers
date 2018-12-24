import arrow
import requests

from commons.projections import ch_to_wgs_lat, ch_to_wgs_lon
from commons.provider import Provider, Status, ProviderException, ureg, Q_, Pressure


class MeteoSwiss(Provider):
    provider_code = 'meteoswiss'
    provider_name = 'meteoswiss.ch'
    provider_url = 'https://www.meteoswiss.admin.ch'

    provider_urls = {
        'default': 'https://www.meteoswiss.admin.ch'
                   '/home/measurement-values.html?param={param}&station={id}',
        'en': 'https://www.meteoswiss.admin.ch'
              '/home/measurement-values.html?param={param}&station={id}',
        'de': 'https://www.meteoschweiz.admin.ch'
              '/home/messwerte.html?param={param}&station={id}',
        'fr': 'https://www.meteosuisse.admin.ch'
              '/home/valeurs-mesurees.html?param={param}&station={id}',
        'it': 'https://www.meteosvizzera.admin.ch'
              '/home/valori-attuali.html?param={param}&station={id}',
    }

    def to_dict(self, features):
        return {feature['id']: feature for feature in features}

    def fix_unit(self, unit):
        return unit.replace('/h', '/hour')

    def get_value(self, properties, unit=None):
        if 'value' in properties:
            if not unit:
                unit = self.fix_unit(properties['unit'])
            return Q_(properties['value'], unit)
        return None

    def process_data(self):
        try:
            self.log.info('Processing MeteoSwiss data...')

            url_pattern = 'https://data.geo.admin.ch/ch.meteoschweiz.messwerte-{parameter}/' \
                          'ch.meteoschweiz.messwerte-{parameter}_en.json'

            main_wind_data = requests.get(url_pattern.format(parameter='windgeschwindigkeit-kmh-10min'),
                                          timeout=(self.connect_timeout, self.read_timeout)).json()['features']
            wind_gust_data = self.to_dict(
                requests.get(url_pattern.format(parameter='wind-boeenspitze-kmh-10min'),
                             timeout=(self.connect_timeout, self.read_timeout)).json()['features'])
            temperature_data = self.to_dict(
                requests.get(url_pattern.format(parameter='lufttemperatur-10min'),
                             timeout=(self.connect_timeout, self.read_timeout)).json()['features'])
            humidity_data = self.to_dict(
                requests.get(url_pattern.format(parameter='luftfeuchtigkeit-10min'),
                             timeout=(self.connect_timeout, self.read_timeout)).json()['features'])
            pressure_data_qfe = self.to_dict(
                requests.get(url_pattern.format(parameter='luftdruck-qfe-10min'),
                             timeout=(self.connect_timeout, self.read_timeout)).json()['features'])
            pressure_data_qnh = self.to_dict(
                requests.get(url_pattern.format(parameter='luftdruck-qnh-10min'),
                             timeout=(self.connect_timeout, self.read_timeout)).json()['features'])
            pressure_data_qff = self.to_dict(
                requests.get(url_pattern.format(parameter='luftdruck-qnh-10min'),
                             timeout=(self.connect_timeout, self.read_timeout)).json()['features'])
            rain_data = self.to_dict(
                requests.get(url_pattern.format(parameter='niederschlag-10min'),
                             timeout=(self.connect_timeout, self.read_timeout)).json()['features'])

            station_id = None
            for meteoswiss_station in main_wind_data:
                try:
                    meteoswiss_id = meteoswiss_station['id']
                    location = meteoswiss_station['geometry']['coordinates']
                    urls = {lang: url.format(param='messwerte-windgeschwindigkeit-kmh-10min', id=meteoswiss_id) for
                            lang, url in self.provider_urls.items()}

                    station = self.save_station(
                        meteoswiss_id,
                        meteoswiss_station['properties']['station_name'],
                        meteoswiss_station['properties']['station_name'],
                        ch_to_wgs_lat(location[0], location[1]),
                        ch_to_wgs_lon(location[0], location[1]),
                        Status.GREEN,
                        altitude=meteoswiss_station['properties']['altitude'],
                        tz='Europe/Zurich',
                        url=urls)
                    station_id = station['_id']

                    key = arrow.get(meteoswiss_station['properties']['reference_ts'], 'YY-MM-DDTHH:mm:ZZ').timestamp

                    measures_collection = self.measures_collection(station_id)
                    new_measures = []

                    if meteoswiss_id in temperature_data:
                        temperature = self.get_value(temperature_data[meteoswiss_id]['properties'], unit=ureg.degC)
                    else:
                        temperature = None

                    if meteoswiss_id in humidity_data:
                        humidity = humidity_data[meteoswiss_id]['properties']['value']
                    else:
                        humidity = None

                    if meteoswiss_id in pressure_data_qfe:
                        pressure = Pressure(
                            qfe=self.get_value(pressure_data_qfe[meteoswiss_id]['properties']),
                            qnh=self.get_value(pressure_data_qnh[meteoswiss_id]['properties']),
                            qff=self.get_value(pressure_data_qff[meteoswiss_id]['properties']))
                    else:
                        pressure = None

                    if meteoswiss_id in rain_data:
                        # 1mm = 1 liter/m^2
                        rain = self.get_value(rain_data[meteoswiss_id]['properties'],
                                              unit=ureg.liter / (ureg.meter ** 2))
                    else:
                        rain = None

                    if not self.has_measure(measures_collection, key):
                        measure = self.create_measure(
                            station,
                            key,
                            meteoswiss_station['properties']['wind_direction'],
                            self.get_value(meteoswiss_station['properties']),
                            self.get_value(wind_gust_data[meteoswiss_id]['properties']),
                            temperature=temperature,
                            humidity=humidity,
                            pressure=pressure,
                            rain=rain
                        )
                        new_measures.append(measure)

                    self.insert_new_measures(measures_collection, station, new_measures)

                except ProviderException as e:
                    self.log.warn(f"Error while processing station '{station_id}': {e}")
                except Exception as e:
                    self.log.exception(f"Error while processing station '{station_id}': {e}")

        except Exception as e:
            self.log.exception(f'Error while processing MeteoSwiss: {e}')

        self.log.info('...Done!')


MeteoSwiss().process_data()
