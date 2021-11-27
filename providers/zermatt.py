import re

import arrow
import psycopg2
import requests
from dateutil import tz
from lxml import html
from psycopg2.extras import RealDictCursor

from settings import ADMIN_DB_URL
from winds_mobi_provider import Provider, ProviderException, StationStatus
from winds_mobi_provider import user_agents


class Zermatt(Provider):
    provider_code = "zermatt"
    provider_name = "zermatt.net"
    provider_url = "http://www.zermatt.net/info/wetter-all.html"

    pylon_pattern = re.compile(r"(Stütze( |\xa0)|(St.( |\xa0)))(?P<pylon>\d+)")
    wind_pattern = re.compile(r"(?P<wind>[0-9]{1,3}) km/h")
    temp_pattern = re.compile(r"(?P<temp>-?[0-9]{1,2})°")

    default_tz = tz.gettz("Europe/Zurich")

    wind_directions = {
        "-": None,
        "N": 0,
        "NO": 1 * (360 / 8),
        "O": 2 * (360 / 8),
        "SO": 3 * (360 / 8),
        "S": 4 * (360 / 8),
        "SW": 5 * (360 / 8),
        "W": 6 * (360 / 8),
        "NW": 7 * (360 / 8),
    }

    def __init__(self, admin_db_url):
        super().__init__()
        self.admin_db_url = admin_db_url

    def get_stations_metadata(self):
        connection = None
        cursor = None
        try:
            connection = psycopg2.connect(self.admin_db_url)
            cursor = connection.cursor(cursor_factory=RealDictCursor)
            cursor.execute("select * from winds_mobi_zermatt_station")
            return cursor.fetchall()
        finally:
            try:
                cursor.close()
                connection.close()
            except Exception:
                pass

    def cleanup_id(self, name):
        return name.strip().replace(" ", "_").replace(".", "_").lower()

    def process_data(self):
        station_id = None
        try:
            self.log.info("Processing Zermatt data...")

            stations_metadata = self.get_stations_metadata()

            session = requests.Session()
            session.headers.update(user_agents.chrome)

            wind_tree = html.fromstring(
                session.get(self.provider_url, timeout=(self.connect_timeout, self.read_timeout)).text
            )

            # Groups
            groups = wind_tree.xpath("//table[@class='w-all']")

            for group in groups:
                stations = group.xpath("tbody/tr")
                i = 0
                while i < len(stations):
                    is_station = stations[i].xpath("td[@class='station']")
                    if len(is_station) == 1:
                        has_data = "kein" not in stations[i + 1].xpath("td")[0].text.lower()
                        try:
                            id_main = self.cleanup_id(stations[i].xpath("td")[0].text)
                            id_subs = []
                            sub_path = stations[i].xpath("td/span")
                            if len(sub_path) > 0:
                                sub_texts = sub_path[0].text.replace("(", "").replace(")", "").split(",")
                                for sub_text in sub_texts:
                                    sub_text = sub_text.strip()
                                    match = self.pylon_pattern.search(sub_text)
                                    if match:
                                        id_subs.append(match["pylon"])
                                    else:
                                        id_subs.append(sub_text)

                            id_sub = "-".join(id_subs)
                            zermatt_id = self.cleanup_id(f"{id_main}-{id_sub}" if id_sub else id_main)

                            try:
                                # Fetch metadata from admin
                                zermatt_station = list(filter(lambda d: str(d["id"]) == zermatt_id, stations_metadata))[
                                    0
                                ]
                            except Exception:
                                continue

                            station = self.save_station(
                                zermatt_id,
                                zermatt_station["name"],
                                zermatt_station["short_name"],
                                zermatt_station["latitude"],
                                zermatt_station["longitude"],
                                StationStatus.GREEN if has_data else StationStatus.RED,
                                altitude=zermatt_station["altitude"] if "altitude" in zermatt_station else None,
                                url=self.provider_url,
                            )
                            station_id = station["_id"]

                            if has_data:
                                key_text = stations[i + 1].xpath("td[@class='c5']")[0].text
                                key = (
                                    arrow.get(key_text.strip(), "DD.MM.YYYY H:mm")
                                    .replace(tzinfo=self.default_tz)
                                    .int_timestamp
                                )

                                measures_collection = self.measures_collection(station_id)
                                if not self.has_measure(measures_collection, key):
                                    wind_dir_text = stations[i + 1].xpath("td[@class='c4']")[0].text
                                    wind_dir = self.wind_directions[wind_dir_text.strip()]

                                    wind_avg_text = stations[i + 1].xpath("td[@class='c3']")[0].text
                                    wind_avg = self.wind_pattern.match(wind_avg_text.strip())["wind"]

                                    # zermatt.net is providing wind_max for the last 3 hours. Using wind_avg instead.
                                    # wind_max_text = stations[i+2].xpath("td[@class='c3']")[0].text
                                    # wind_max = self.wind_pattern.match(wind_max_text.strip())['wind']

                                    temp_text = stations[i + 1].xpath("td[@class='c2']")[0].text
                                    temp = self.temp_pattern.match(temp_text.strip())["temp"] if temp_text else None

                                    measure = self.create_measure(
                                        station, key, wind_dir, wind_avg, wind_avg, temperature=temp
                                    )
                                    self.insert_new_measures(measures_collection, station, [measure])
                            else:
                                self.log.warning(f"No data for station '{station_id}'")
                        except ProviderException as e:
                            self.log.warning(f"Error while processing station '{station_id}': {e}")
                        except Exception as e:
                            self.log.exception(f"Error while processing station '{station_id}': {e}")
                        finally:
                            if has_data:
                                i += 4
                            else:
                                i += 2
                    else:
                        raise ProviderException("Invalid html table order")

        except Exception as e:
            self.log.exception(f"Error while processing Zermatt: {e}")


if __name__ == "__main__":
    Zermatt(ADMIN_DB_URL).process_data()
