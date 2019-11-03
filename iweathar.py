import arrow
import requests
import urllib3
from dateutil import tz
from lxml import etree

from commons.provider import Provider, Status, ProviderException
from commons.provider import Q_, ureg, Pressure
from settings import IWEATHAR_KEY

# Disable urllib3 warning because https://iweathar.co.za has a certificates chain issue
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class IWeathar(Provider):
    provider_code = 'iweathar'
    provider_name = 'iweathar.co.za'
    provider_url = 'https://iweathar.co.za'

    def __init__(self):
        super().__init__()
        self.iweathar_key = IWEATHAR_KEY

    def process_data(self):
        try:
            self.log.info('Processing iWeathar data...')

            result_tree = etree.parse(
                requests.get(f'https://iweathar.co.za/live_data.php?unit=kmh&key={self.iweathar_key}',
                             stream=True, verify=False,
                             timeout=(self.connect_timeout, self.read_timeout)).raw)

            iweathar_tz = tz.gettz('Africa/Johannesburg')

            for item in result_tree.xpath('//ITEM'):
                station_id = None
                try:
                    iweathar_id = item.xpath('STATION_ID')[0].text
                    name = item.xpath('LOCATION')[0].text
                    status = Status.GREEN if item.xpath('STATUS')[0].text == 'ON-LINE' else Status.RED

                    station = self.save_station(
                        iweathar_id,
                        name,
                        name,
                        item.xpath('LAT')[0].text,
                        item.xpath('LONG')[0].text,
                        status,
                        url=f'{self.provider_url}/display?s_id={iweathar_id}'
                    )
                    station_id = station['_id']

                    wind_dir_attr = item.xpath('WIND_ANG')
                    wind_avg_attr = item.xpath('WIND_AVG')
                    wind_max_attr = item.xpath('WIND_MAX')
                    if not (wind_dir_attr and wind_avg_attr and wind_max_attr):
                        self.log.warning(f"Station '{station_id}' has no wind measures")
                        continue

                    key = arrow.get(
                        item.xpath('LASTUPDATE')[0].text, 'YYYY-MM-DD HH:mm:ss').replace(tzinfo=iweathar_tz).timestamp

                    measures_collection = self.measures_collection(station_id)
                    if not self.has_measure(measures_collection, key):
                        try:
                            temperature_attr = item.xpath('TEMPERATURE_C')
                            if temperature_attr and temperature_attr[0].text:
                                temperature = Q_(temperature_attr[0].text, ureg.degC)
                            else:
                                temperature = None

                            humidity_attr = item.xpath('HUMIDITY_PERC')
                            if humidity_attr and humidity_attr[0].text:
                                humidity = humidity_attr[0].text
                            else:
                                humidity = None

                            pressure_attr = item.xpath('PRESSURE_MB')
                            if pressure_attr and pressure_attr[0].text:
                                pressure = Pressure(qfe=pressure_attr[0].text, qnh=None, qff=None)
                            else:
                                pressure = None

                            rain_attr = item.xpath('RAINFALL_MM')
                            if rain_attr and rain_attr[0].text:
                                rain = Q_(rain_attr[0].text, ureg.liter / (ureg.meter ** 2))
                            else:
                                rain = None

                            measure = self.create_measure(
                                station,
                                key,
                                wind_dir_attr[0].text,
                                wind_avg_attr[0].text,
                                wind_max_attr[0].text,
                                temperature=temperature,
                                humidity=humidity,
                                pressure=pressure,
                                rain=rain
                            )
                            self.insert_new_measures(measures_collection, station, [measure])
                        except ProviderException as e:
                            self.log.warning(f"Error while processing measure '{key}' for station '{station_id}': {e}")
                        except Exception as e:
                            self.log.exception(
                                f"Error while processing measure '{key}' for station '{station_id}': {e}")

                except ProviderException as e:
                    self.log.warning(f"Error while processing station '{station_id}': {e}")
                except Exception as e:
                    self.log.exception(f"Error while processing station '{station_id}': {e}")

        except Exception as e:
            self.log.exception(f'Error while processing iWeathar: {e}')

        self.log.info('...Done!')


IWeathar().process_data()
