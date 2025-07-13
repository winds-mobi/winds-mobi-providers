import re
from zoneinfo import ZoneInfo

import arrow
import psycopg2
import requests
from lxml import html
from psycopg2.extras import DictCursor

from settings import ADMIN_DB_URL
from winds_mobi_provider import Provider, ProviderException, StationNames, StationStatus, user_agents


class Zermatt(Provider):
    provider_code = "zermatt"
    provider_name = "zermatt.net"
    provider_url = "https://www.zermatt.net/info/wetter-all.html"
    timezone = ZoneInfo("Europe/Zurich")

    pylon_pattern = re.compile(r"(Stütze( |\xa0)|(St.( |\xa0)))(?P<pylon>\d+)")
    wind_pattern = re.compile(r"(?P<wind>[0-9]{1,3}) km/h")
    temp_pattern = re.compile(r"(?P<temp>-?[0-9]{1,2})°")

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
            cursor = connection.cursor(cursor_factory=DictCursor)
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

            groups = wind_tree.xpath("//table[@class='w-all']")

            for group in groups:
                table_rows = group.xpath("tbody/tr")
                i = 0
                while i < len(table_rows):
                    next_cell = table_rows[i + 1].xpath("td")
                    if next_cell[0].attrib["class"] == "c1":
                        has_data = True
                        next_row = 4
                    elif next_cell[0].attrib["class"] == "c5":
                        has_data = False
                        next_row = 2
                    elif next_cell[0].attrib["class"] == "station":
                        has_data = False
                        next_row = 1
                    else:
                        raise ProviderException("Unexpected table rows")

                    try:
                        id_main = self.cleanup_id(table_rows[i].xpath("td")[0].text)
                        id_subs = []
                        sub_path = table_rows[i].xpath("td/span")
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
                            zermatt_station = next(filter(lambda s: str(s["id"]) == zermatt_id, stations_metadata))
                        except Exception:
                            continue

                        station = self.save_station(
                            zermatt_id,
                            StationNames(zermatt_station["short_name"], zermatt_station["name"]),
                            zermatt_station["latitude"],
                            zermatt_station["longitude"],
                            StationStatus.GREEN if has_data else StationStatus.RED,
                            altitude=zermatt_station["altitude"] if "altitude" in zermatt_station else None,
                            url=self.provider_url,
                        )
                        station_id = station["_id"]

                        if has_data:
                            key_text = table_rows[i + 1].xpath("td[@class='c5']")[0].text
                            key = (
                                arrow.get(key_text.strip(), "DD.MM.YYYY H:mm")
                                .replace(tzinfo=self.timezone)
                                .int_timestamp
                            )

                            if not self.has_measure(station, key):
                                # class="wCurr"
                                wind_dir_text = table_rows[i + 1].xpath("td[@class='c4']")[0].text
                                if wind_dir_text == "-":
                                    raise ProviderException("No wind direction")
                                wind_dir = self.wind_directions[wind_dir_text.strip()]

                                # class="wAvr"
                                wind_avg_text = table_rows[i + 3].xpath("td[@class='c3']")[0].text
                                if wind_avg_text == "-":
                                    raise ProviderException("No wind average")
                                wind_avg = self.wind_pattern.match(wind_avg_text.strip())["wind"]

                                # class="wMax"
                                wind_max_text = table_rows[i + 2].xpath("td[@class='c3']")[0].text
                                if wind_max_text == "-":
                                    raise ProviderException("No wind max")
                                wind_max = self.wind_pattern.match(wind_max_text.strip())["wind"]

                                temp_text = table_rows[i + 1].xpath("td[@class='c2']")[0].text
                                temp = self.temp_pattern.match(temp_text.strip())["temp"] if temp_text else None

                                measure = self.create_measure(
                                    station, key, wind_dir, wind_avg, wind_max, temperature=temp
                                )
                                self.insert_measures(station, measure)
                        else:
                            self.log.warning(f"No data for station '{station_id}'")
                    except ProviderException as e:
                        self.log.warning(f"Error while processing station '{station_id}': {e}")
                    except Exception as e:
                        self.log.exception(f"Error while processing station '{station_id}': {e}")
                    finally:
                        i += next_row

        except Exception as e:
            self.log.exception(f"Error while processing Zermatt: {e}")


def zermatt():
    Zermatt(ADMIN_DB_URL).process_data()


if __name__ == "__main__":
    zermatt()
