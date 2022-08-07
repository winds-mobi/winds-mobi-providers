import arrow
import psycopg2
import requests
from psycopg2.extras import DictCursor

import settings
from winds_mobi_provider import Pressure, Provider, ProviderException, Q_, StationStatus, ureg


class Windy(Provider):
    provider_code = "windy"
    provider_name = "windy.com"
    provider_url = "https://windy.com"

    def __init__(self, api_key, admin_db_url):
        super().__init__()
        self.api_key = api_key
        self.admin_db_url = admin_db_url

    def get_stations_metadata(self):
        connection = None
        cursor = None
        try:
            connection = psycopg2.connect(self.admin_db_url)
            cursor = connection.cursor(cursor_factory=DictCursor)
            cursor.execute("select * from winds_mobi_windy_station")
            return cursor.fetchall()
        finally:
            try:
                cursor.close()
                connection.close()
            except Exception:
                pass

    def process_data(self):
        windy_ids = list(map(lambda s: str(s["id"]), self.get_stations_metadata()))

        stations = {}
        try:
            self.log.info("Processing Windy data...")

            result = requests.get(
                f"https://stations.windy.com/pws/stations/{self.api_key}",
                timeout=(self.connect_timeout, self.read_timeout),
            )
            windy_stations = result.json()["header"]

            for windy_station in filter(lambda s: s["id"] in windy_ids, windy_stations):
                windy_id = None
                try:
                    windy_id = windy_station["id"]
                    station = self.save_station(
                        windy_id,
                        windy_station["name"],
                        None,
                        windy_station["lat"],
                        windy_station["lon"],
                        StationStatus.GREEN,
                        altitude=windy_station["elev_m"],
                        url=f"{self.provider_url}/station/pws-{windy_id}",
                    )
                    stations[windy_id] = station

                except ProviderException as e:
                    self.log.warning(f"Error while processing station '{windy_id}': {e}")
                except Exception as e:
                    self.log.exception(f"Error while processing station '{windy_id}': {e}")

        except ProviderException as e:
            self.log.warning(f"Error while processing stations: {e}")
        except Exception as e:
            self.log.exception(f"Error while processing stations: {e}")

        for windy_id, station in stations.items():
            station_id = station["_id"]
            try:
                result = requests.get(
                    f"https://stations.windy.com/pws/station/open/{self.api_key}/{windy_id}",
                    timeout=(self.connect_timeout, self.read_timeout),
                )
                windy_measures = result.json()["data"]
                if not windy_measures:
                    continue

                measures_collection = self.measures_collection(station_id)
                new_measures = []
                for index, ts in enumerate(windy_measures["ts"]):
                    key = arrow.get(ts).int_timestamp
                    wind_direction = windy_measures["windDir"][index]
                    wind_average = windy_measures["wind"][index]
                    wind_maximum = windy_measures["gust"][index]
                    if (
                        wind_direction is not None
                        and wind_average is not None
                        and wind_maximum is not None
                        and not self.has_measure(measures_collection, key)
                    ):
                        new_measures.append(
                            self.create_measure(
                                station,
                                key,
                                wind_direction,
                                Q_(wind_average, ureg.meter / ureg.second),
                                Q_(wind_maximum, ureg.meter / ureg.second),
                                temperature=windy_measures["temp"][index] if "temp" in windy_measures else None,
                                pressure=Pressure(
                                    qfe=Q_(windy_measures["pressure"][index] / 1000, ureg.hPa)
                                    if windy_measures["pressure"][index] is not None
                                    else None,
                                    qnh=None,
                                    qff=None,
                                )
                                if "pressure" in windy_measures
                                else None,
                            )
                        )
                self.insert_new_measures(measures_collection, station, new_measures)

            except ProviderException as e:
                self.log.warning(f"Error while processing measures for station '{station_id}': {e}")
            except Exception as e:
                self.log.exception(f"Error while processing measures for station '{station_id}': {e}")

        self.log.info("...Done!")


def windy():
    Windy(settings.WINDY_API_KEY, settings.ADMIN_DB_URL).process_data()


if __name__ == "__main__":
    windy()
