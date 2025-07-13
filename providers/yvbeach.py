import re
from zoneinfo import ZoneInfo

import arrow
import requests

from winds_mobi_provider import Provider, ProviderException, StationNames, StationStatus, user_agents


class YVBeach(Provider):
    provider_code = "yvbeach"
    provider_name = "yvbeach.com"
    provider_url = "http://www.yvbeach.com/yvmeteo.htm"
    timezone = ZoneInfo("Europe/Zurich")

    def process_data(self):
        station_id = "yvbeach"
        try:
            self.log.info("Processing yvbeach data...")

            date_pattern = re.compile(r"Relevés du<br/>(?P<date>.*?) à (?P<time>.*?)<br/>")
            wind_pattern = re.compile(
                r"<b>VENT</b><br/>"
                r"Moy10min <b>(?P<wind_avg>[0-9]{1,3}\.[0-9]) km/h</b><br/>"
                r"Max/1h <b>(?P<wind_max>[0-9]{1,3}\.[0-9]) km/h<br/>"
                r"[A-Z]{1,3} - (?P<wind_dir>[0-9]{1,3})°"
            )
            temp_pattern = re.compile(r"<b>TEMPERATURES<br/>Air (?P<temp>[-+]?[0-9]*\.?[0-9]+)°C")

            session = requests.Session()
            session.headers.update(user_agents.chrome)
            content = session.get(
                "http://www.yvbeach.com/yvmeteo.wml", timeout=(self.connect_timeout, self.read_timeout)
            ).text.replace("\r\n", "")

            station = self.save_station(
                "yvbeach",
                StationNames(short_name="yvbeach", name="Yvonand plage"),
                46.805410,
                6.714839,
                StationStatus.GREEN,
                url=self.provider_url,
            )
            station_id = station["_id"]

            date = date_pattern.search(content).groupdict()
            key = (
                arrow.get(f'{date["date"]} {date["time"]}', "DD.MM.YYYY HH[h]mm")
                .replace(tzinfo=self.timezone)
                .int_timestamp
            )

            if not self.has_measure(station, key):
                wind = wind_pattern.search(content).groupdict()
                temp = temp_pattern.search(content).groupdict()

                measure = self.create_measure(
                    station,
                    key,
                    wind["wind_dir"],
                    wind["wind_avg"],
                    wind["wind_max"],
                    temperature=temp["temp"],
                )
                self.insert_measures(station, measure)

        except ProviderException as e:
            self.log.warning(f"Error while processing station '{station_id}': {e}")
        except Exception as e:
            self.log.exception(f"Error while processing station '{station_id}': {e}")

        self.log.info("...Done!")


def yvbeach():
    YVBeach().process_data()


if __name__ == "__main__":
    yvbeach()
