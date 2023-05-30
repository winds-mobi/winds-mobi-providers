import arrow
import requests

from winds_mobi_provider import Provider, StationStatus, ureg, Q_, Pressure


class GxAircom(Provider):
    provider_code = "gxaircom"
    provider_name = "gxaircom.com"

    def process_data(self):
        self.log.info("Processing GxAircom data...")
        try:
            data = requests.get(
                "http://www.mgenet.at/gxaircom/stations.php", timeout=(self.connect_timeout, self.read_timeout)
            ).json()
            for station in data:
                try:
                    winds_station = self.save_station(
                        provider_id=station["stationId"],
                        short_name=station["stationName"],
                        name=None,  # Lets winds.mobi provide the full name with the help of Google Geocoding API
                        default_name=station["stationName"],
                        latitude=station["lat"],
                        longitude=station["lon"],
                        status=StationStatus.GREEN if station["online"] == "1" else StationStatus.RED,
                        altitude=station["alt"],
                        url="http://www.mgenet.at/gxaircom/stationstable.php",
                    )
                    measure_key = arrow.get(station["DT"], "YYYY-MM-DD HH:mm:ss").int_timestamp
                    measures_collection = self.measures_collection(winds_station["_id"])

                    if not self.has_measure(measures_collection, measure_key):
                        new_measure = self.create_measure(
                            for_station=winds_station,
                            _id=measure_key,
                            wind_direction=station["wDir"],
                            wind_average=Q_(station["wSpeed"], ureg.kilometer / ureg.hour),
                            wind_maximum=Q_(station["wGust"], ureg.kilometer / ureg.hour),
                            temperature=Q_(station["temp"], ureg.degC) if station["temp"] is not None else None,
                            pressure=Pressure(station["pressure"], qnh=None, qff=None)
                            if station["pressure"] is not None
                            else None,
                        )
                        self.insert_new_measures(measures_collection, winds_station, [new_measure])
                except Exception as e:
                    self.log.exception(
                        f"Error while processing station {station['stationId']}({station['stationName']}): {e}"
                    )
        except Exception as e:
            self.log.exception(f"Error while processing MyProvider: {e}")
        self.log.info("...Done !")


def gxaircom():
    GxAircom().process_data()


if __name__ == "__main__":
    gxaircom()
