import arrow
import psycopg2
import requests
from psycopg2.extras import DictCursor

import settings
from winds_mobi_provider import Q_, Pressure, Provider, ProviderException, StationNames, StationStatus, ureg


class WUnderground(Provider):
    provider_code = "wunderground"
    provider_name = "wunderground.com"
    provider_url = "https://www.wunderground.com"

    def __init__(self, admin_db_url):
        super().__init__()
        self.admin_db_url = admin_db_url

    def get_stations_metadata(self):
        connection = None
        cursor = None
        try:
            connection = psycopg2.connect(self.admin_db_url)
            cursor = connection.cursor(cursor_factory=DictCursor)
            cursor.execute("select * from winds_mobi_wunderground_station")
            return cursor.fetchall()
        finally:
            try:
                cursor.close()
                connection.close()
            except Exception:
                pass

    def process_data(self):
        self.log.info("Processing WUnderground data...")
        try:
            wu_station_ids = list(map(lambda s: s["id"], self.get_stations_metadata()))

            for wu_station_id in wu_station_ids:
                url = (
                    "https://api.weather.com/v2/pws/observations/current"
                    # the API key didn't change for years
                    + "?apiKey=e1f10a1e78da46f5b10a1e78da96f525"
                    + f"&stationId={wu_station_id}"
                    + "&format=json"
                    + "&units=m"
                )
                data = requests.get(url, timeout=(self.connect_timeout, self.read_timeout)).json()
                # data sample:
                # {
                #     "observations": [
                #         {
                #             "stationID": "INZIDE9",
                #             "obsTimeUtc": "2024-07-31T16:34:50Z",
                #             "obsTimeLocal": "2024-07-31 18:34:50",
                #             "neighborhood": "Nüziders",
                #             "softwareType": "EasyWeatherPro_V5.1.3",
                #             "country": "AT",
                #             "solarRadiation": 3.4,
                #             "lon": 9.802861,
                #             "realtimeFrequency": null,
                #             "epoch": 1722443690,
                #             "lat": 47.1663,
                #             "uv": 0,
                #             "winddir": 240,
                #             "humidity": 94,
                #             "qcStatus": 1,
                #             "metric": {
                #                 "temp": 19,
                #                 "heatIndex": 19,
                #                 "dewpt": 18,
                #                 "windChill": 19,
                #                 "windSpeed": 3,
                #                 "windGust": 4,
                #                 "pressure": 1015.41,
                #                 "precipRate": 19.81,
                #                 "precipTotal": 17.3,
                #                 "elev": 549
                #             }
                #         }
                #     ]
                # }

                for current_observation in data["observations"]:
                    try:
                        winds_station = self.save_station(
                            provider_id=current_observation["stationID"],
                            names=lambda names: StationNames(
                                short_name=current_observation["neighborhood"],
                                name=names.name or current_observation["neighborhood"],
                            ),
                            latitude=current_observation["lat"],
                            longitude=current_observation["lon"],
                            status=StationStatus.GREEN if current_observation["qcStatus"] == 1 else StationStatus.RED,
                            url={
                                "default": f"{self.provider_url}/dashboard/pws/{current_observation['stationID']}",
                            },
                        )
                        station_id = winds_station["_id"]

                        # remove the seconds -> only store one measure per minute at max.
                        measure_key = (
                            arrow.get(current_observation["obsTimeUtc"], "YYYY-MM-DDTHH:mm:ssZ")
                            .replace(second=0)
                            .int_timestamp
                        )

                        if not self.has_measure(winds_station, measure_key):
                            try:
                                new_measure = self.create_measure(
                                    station=winds_station,
                                    _id=measure_key,
                                    wind_direction=current_observation["winddir"],
                                    wind_average=Q_(
                                        current_observation["metric"]["windSpeed"], ureg.kilometer / ureg.hour
                                    ),
                                    wind_maximum=Q_(
                                        current_observation["metric"]["windGust"], ureg.kilometer / ureg.hour
                                    ),
                                    temperature=Q_(current_observation["metric"]["temp"], ureg.degC),
                                    pressure=Pressure(current_observation["metric"]["pressure"], qnh=None, qff=None),
                                )
                                self.insert_measures(winds_station, new_measure)
                            except ProviderException as e:
                                self.log.warning(
                                    f"Error while processing measure '{measure_key}' for station '{station_id}': {e}"
                                )
                            except Exception as e:
                                self.log.exception(
                                    f"Error while processing measure '{measure_key}' for station '{station_id}': {e}"
                                )

                    except ProviderException as e:
                        self.log.warning(f"Error while processing station '{wu_station_id}': {e}")
                    except Exception as e:
                        self.log.exception(f"Error while processing station '{wu_station_id}': {e}")

        except Exception as e:
            self.log.exception(f"Error while processing WUndergroundProvider: {e}")

        self.log.info("...Done !")


def wunderground():
    WUnderground(settings.ADMIN_DB_URL).process_data()


if __name__ == "__main__":
    wunderground()
