from zoneinfo import ZoneInfo

import requests

from winds_mobi_provider import Q_, Pressure, Provider, ProviderException, StationNames, StationStatus, ureg


class PgSonda(Provider):
    provider_code = "pgsonda"
    provider_name = "pgsonda.cz"
    provider_url = "https://pgsonda.cz"

    timezone = ZoneInfo("Europe/Zurich")

    def process_data(self):
        self.log.info("Processing PGsonda data...")

        try:
            api_url = "https://pgsonda.cz/api/api_json_complete.php?limit=1"
            response = requests.get(api_url, timeout=(self.connect_timeout, self.read_timeout))
            response.raise_for_status()

            stations_raw = response.json()

            data = []
            for rec in stations_raw:
                try:
                    station_id = rec["device"]
                    short_name = rec["webname"]
                    long_name = rec["webname"]

                    latitude = float(rec.get("gps_lat", 0.0))
                    longitude = float(rec.get("gps_lng", 0.0))
                    altitude = float(rec.get("amsl", 0.0))

                    ts = rec["db_epoch"]

                    # Convert m/s → km/h
                    wind_avg_kmh = float(rec.get("avg_avgspd", 0.0)) * 3.6
                    wind_max_kmh = float(rec.get("avg_maxspd", 0.0)) * 3.6
                    wind_dir_deg = float(rec.get("avg_avgdir", 0.0))

                    temp_c = float(rec.get("avg_temp", 0.0))
                    humidity = float(rec.get("avg_hum", 0.0))
                    pressure_pa = float(rec.get("avg_preszero", 0.0))
                    rain = float(rec.get("avg_rain_hour", 0.0))

                    data.append(
                        {
                            "id": station_id,
                            "shortName": short_name,
                            "name": long_name,
                            "latitude": latitude,
                            "longitude": longitude,
                            "status": "ok",
                            "altitude": altitude,
                            "measures": [
                                {
                                    "time": ts,
                                    "windDirection": wind_dir_deg,
                                    "windAverage": wind_avg_kmh,
                                    "windMaximum": wind_max_kmh,
                                    "temperature": temp_c,
                                    "pressure": pressure_pa,
                                    "humidity": humidity,
                                    "rain": rain,
                                }
                            ],
                        }
                    )

                except KeyError as e:
                    self.log.warning(f"Skipping station record due to missing field: {e}")
                except Exception as e:
                    self.log.exception(f"Error while mapping station '{rec.get('name', '<unknown>')}': {e}")

            for station in data:
                try:
                    winds_station = self.save_station(
                        provider_id=station["id"],
                        names=StationNames(short_name=station["shortName"], name=station["name"]),
                        latitude=station["latitude"],
                        longitude=station["longitude"],
                        altitude=station["altitude"],
                        status=StationStatus.GREEN if station["status"] == "ok" else StationStatus.RED,
                        url=f"{self.provider_url}/{station['id']}",
                    )

                    measure_key = station["measures"][0]["time"]
                    if not measure_key:
                        continue

                    measures_collection = self.measures_collection(winds_station["_id"])

                    if not self.has_measure(measures_collection, measure_key):
                        new_measure = self.create_measure(
                            for_station=winds_station,
                            _id=measure_key,
                            wind_direction=station["measures"][0]["windDirection"],
                            wind_average=Q_(station["measures"][0]["windAverage"], ureg.kilometer / ureg.hour),
                            wind_maximum=Q_(station["measures"][0]["windMaximum"], ureg.kilometer / ureg.hour),
                            temperature=Q_(station["measures"][0]["temperature"], ureg.degC),
                            pressure=Pressure(station["measures"][0]["pressure"], qnh=None, qff=None),
                            humidity=station["measures"][0]["humidity"],
                            rain=station["measures"][0]["rain"],
                        )
                        self.insert_new_measures(measures_collection, winds_station, [new_measure])

                except ProviderException as e:
                    self.log.warning(f"Error while processing station '{station['id']}': {e}")
                except Exception as e:
                    self.log.exception(f"Error while processing station '{station['id']}': {e}")

        except Exception as e:
            self.log.exception(f"Error while processing PGsonda: {e}")

        self.log.info("...Done !")


def pgsonda():
    PgSonda().process_data()


if __name__ == "__main__":
    pgsonda()
