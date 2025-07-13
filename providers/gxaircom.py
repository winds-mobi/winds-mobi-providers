import arrow
import requests

from winds_mobi_provider import Q_, Pressure, Provider, StationNames, StationStatus, ureg


class Gxaircom(Provider):
    provider_code = "gxaircom"
    provider_name = "gxaircom.net"
    provider_url = "http://www.gxaircom.net/gxaircom/stationstable.php"

    def process_data(self):
        self.log.info("Processing Gxaircom data...")
        try:
            data = requests.get(
                "http://www.gxaircom.net/gxaircom/stations.php", timeout=(self.connect_timeout, self.read_timeout)
            ).json()
            for station in data:
                try:
                    winds_station = self.save_station(
                        provider_id=station["stationId"],
                        names=lambda names: StationNames(
                            short_name=station["stationName"], name=names.name or station["stationName"]
                        ),
                        latitude=station["lat"],
                        longitude=station["lon"],
                        status=StationStatus.GREEN if station["online"] == "1" else StationStatus.RED,
                        altitude=station["alt"],
                    )
                    measure_key = arrow.get(station["DT"], "YYYY-MM-DD HH:mm:ss").int_timestamp

                    if not self.has_measure(winds_station, measure_key):
                        measure = self.create_measure(
                            station=winds_station,
                            _id=measure_key,
                            wind_direction=station["wDir"],
                            wind_average=Q_(station["wSpeed"], ureg.kilometer / ureg.hour),
                            wind_maximum=Q_(station["wGust"], ureg.kilometer / ureg.hour),
                            temperature=Q_(station["temp"], ureg.degC) if station["temp"] is not None else None,
                            pressure=(
                                Pressure(station["pressure"], qnh=None, qff=None)
                                if station["pressure"] is not None
                                else None
                            ),
                        )
                        self.insert_measures(winds_station, measure)
                except Exception as e:
                    self.log.exception(
                        f"Error while processing station {station['stationId']}({station['stationName']}): {e}"
                    )
        except Exception as e:
            self.log.exception(f"Error while processing MyProvider: {e}")
        self.log.info("...Done !")


def gxaircom():
    Gxaircom().process_data()


if __name__ == "__main__":
    gxaircom()
