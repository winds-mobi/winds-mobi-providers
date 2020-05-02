import re

import arrow
import requests
from dateutil import tz

from winds_mobi_provider import Provider, StationStatus, ProviderException
from winds_mobi_provider import user_agents


class YVBeach(Provider):
    provider_code = 'yvbeach'
    provider_name = 'yvbeach.com'
    provider_url = 'http://www.yvbeach.com/yvmeteo.htm'

    def process_data(self):
        station_id = 'yvbeach'
        try:
            self.log.info('Processing yvbeach data...')

            date_pattern = re.compile(r'Relevés du<br/>(?P<date>.*?) à (?P<time>.*?)<br/>')
            wind_pattern = re.compile(r'<b>VENT</b><br/>'
                                      r'Moy10min <b>(?P<wind_avg>[0-9]{1,3}\.[0-9]) km/h</b><br/>'
                                      r'Max/1h <b>(?P<wind_max>[0-9]{1,3}\.[0-9]) km/h<br/>'
                                      r'[A-Z]{1,3} - (?P<wind_dir>[0-9]{1,3})°')
            temp_pattern = re.compile(r'<b>TEMPERATURES<br/>Air (?P<temp>[-+]?[0-9]*\.?[0-9]+)°C')

            yvbeach_tz = tz.gettz('Europe/Zurich')

            session = requests.Session()
            session.headers.update(user_agents.chrome)
            content = session.get('http://www.yvbeach.com/yvmeteo.wml',
                                  timeout=(self.connect_timeout, self.read_timeout)).text.replace('\r\n', '')

            station = self.save_station(
                'yvbeach',
                'yvbeach',
                'Yvonand plage',
                float(46.805410),
                float(6.714839),
                StationStatus.GREEN,
                url=self.provider_url
            )
            station_id = station['_id']

            date = date_pattern.search(content).groupdict()
            key = arrow.get(f'{date["date"]} {date["time"]}', 'DD.MM.YYYY HH[h]mm').replace(
                tzinfo=yvbeach_tz).timestamp

            measures_collection = self.measures_collection(station_id)
            new_measures = []

            if not self.has_measure(measures_collection, key):
                wind = wind_pattern.search(content).groupdict()
                temp = temp_pattern.search(content).groupdict()

                measure = self.create_measure(
                    station,
                    key,
                    wind['wind_dir'],
                    wind['wind_avg'],
                    wind['wind_max'],
                    temperature=temp['temp'],
                )
                new_measures.append(measure)

            self.insert_new_measures(measures_collection, station, new_measures)

        except ProviderException as e:
            self.log.warning(f"Error while processing station '{station_id}': {e}")
        except Exception as e:
            self.log.exception(f"Error while processing station '{station_id}': {e}")

        self.log.info('...Done!')


if __name__ == '__main__':
    YVBeach().process_data()
