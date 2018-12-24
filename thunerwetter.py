import re

import arrow
import requests
from dateutil import tz
from lxml import html

from commons import user_agents
from commons.provider import Provider, Status, ProviderException


class ThunerWetter(Provider):
    provider_code = 'thunerwetter'
    provider_name = 'thunerwetter.ch'
    provider_url = 'http://www.thunerwetter.ch/wind.html'
    provider_url_temp = 'http://www.thunerwetter.ch/temp.html'

    def process_data(self):
        station_id = None
        try:
            self.log.info('Processing Thunerwetter data...')

            date_pattern = re.compile(r'am (?P<date>.*?) um (?P<time>.*?) Uhr')
            wind_pattern = re.compile(r'(?P<wind_speed>[0-9]{1,3}\.[0-9]) km/h / '
                                      r'(?P<wind_dir>[A-Z]{1,2}(-[A-Z]{1,2})?)')
            wind_directions = {
                'N': 0,
                'N-NO': 1 * (360 / 16),
                'NO': 2 * (360 / 16),
                'O-NO': 3 * (360 / 16),
                'O': 4 * (360 / 16),
                'O-SO': 5 * (360 / 16),
                'SO': 6 * (360 / 16),
                'S-SO': 7 * (360 / 16),
                'S': 8 * (360 / 16),
                'S-SW': 9 * (360 / 16),
                'SW': 10 * (360 / 16),
                'W-SW': 11 * (360 / 16),
                'W': 12 * (360 / 16),
                'W-NW': 13 * (360 / 16),
                'NW': 14 * (360 / 16),
                'N-NW': 15 * (360 / 16),
            }
            temp_pattern = re.compile(r'(?P<temp>[-+]?[0-9]{1,3}\.[0-9]) °C')
            humidity_pattern = re.compile(r'(?P<humidity>[0-9]{1,3}) %')

            thun_tz = tz.gettz('Europe/Zurich')

            session = requests.Session()
            session.headers.update(user_agents.chrome)

            wind_tree = html.fromstring(
                session.get(self.provider_url, timeout=(self.connect_timeout, self.read_timeout)).text)

            # Date
            date_element = wind_tree.xpath('//td[text()[contains(.,"Messwerte von Thun")]]')[0]
            date_text = date_element.text.strip()
            date = date_pattern.search(date_text).groupdict()

            station = self.save_station(
                'westquartier',
                'Thun Westquartier',
                'Thun Westquartier',
                float(46.7536663),
                float(7.6211841),
                Status.GREEN,
                url=self.provider_url
            )
            station_id = station['_id']

            key = arrow.get(f'{date["date"]} {date["time"]}', 'DD.MM.YYYY HH[:]mm').replace(
                tzinfo=thun_tz).timestamp

            measures_collection = self.measures_collection(station_id)
            new_measures = []

            if not self.has_measure(measures_collection, key):
                wind_elements = wind_tree.xpath('//td[text()="Ø 10 Minuten"]')

                # Wind average
                wind_avg_text = wind_elements[0].xpath('following-sibling::td')[0].text.strip()
                wind_avg = wind_pattern.search(wind_avg_text).groupdict()

                # Wind max
                wind_max_text = wind_elements[1].xpath('following-sibling::td')[0].text.strip()
                wind_max = wind_pattern.search(wind_max_text).groupdict()

                air_tree = html.fromstring(
                    session.get(self.provider_url_temp, timeout=(self.connect_timeout, self.read_timeout)).text)

                # Date
                date_element = air_tree.xpath('//td[text()[contains(.,"Messwerte von Thun")]]')[0]
                date_text = date_element.text.strip()
                date = date_pattern.search(date_text).groupdict()
                air_date = arrow.get(f'{date["date"]} {date["time"]}', 'DD.MM.YYYY HH[:]mm').replace(
                    tzinfo=thun_tz).timestamp

                if air_date != key:
                    raise ProviderException('Wind and air dates are not matching')

                air_elements = air_tree.xpath('//td[text()="aktuell"]')

                # Temperature
                temp_text = air_elements[0].xpath('following-sibling::td')[0].text.strip()
                temp = temp_pattern.search(temp_text).groupdict()

                # Humidity
                humidity_text = air_elements[1].xpath('following-sibling::td')[0].text.strip()
                humidity = humidity_pattern.search(humidity_text).groupdict()

                measure = self.create_measure(
                    station,
                    key,
                    wind_directions[wind_avg['wind_dir']],
                    wind_avg['wind_speed'],
                    wind_max['wind_speed'],
                    temperature=temp['temp'],
                    humidity=humidity['humidity']
                )
                new_measures.append(measure)

            self.insert_new_measures(measures_collection, station, new_measures)

        except ProviderException as e:
            self.log.warn(f"Error while processing station '{station_id}': {e}")
        except Exception as e:
            self.log.exception(f"Error while processing station '{station_id}': {e}")

        self.log.info('...Done!')


ThunerWetter().process_data()
