import arrow
import requests

from winds_mobi_provider import Q_, Pressure, Provider, ProviderException, StationNames, StationStatus, ureg


# api doc: https://developers.pioupiou.fr/api/live/
class OpenWindMap(Provider):
    provider_code = "openwindmap"
    provider_name = "api.pioupiou.fr"
    provider_url = "https://api.pioupiou.fr/v1/live"

    def process_data(self):
        self.log.info("Processing openwindmap data...")
        try:
            data = requests.get(f"{self.provider_url}/all", timeout=(self.connect_timeout, self.read_timeout)).json()

            for station in data["data"]:
                try:
                    winds_station = self.save_station(
                        provider_id=station["id"],
                        # Let winds.mobi provide the full name (if found) with the help of Google Geocoding API
                        names=lambda names: StationNames(
                            short_name=station["meta"]["name"], name=names.name or station["meta"]["name"]
                        ),
                        latitude=station["location"]["latitude"],
                        longitude=station["location"]["longitude"],
                        status=StationStatus.GREEN if station["status"]["state"] == "on" else StationStatus.RED,
                        # If url is a dict, the keys must correspond to an ISO 639-1 language code. It also needs a
                        # "default" key, "english" if available. Here an example:
                        url={"default": f"{self.provider_url}/{station['id']}"},
                    )
                    station_id = winds_station["_id"]

                    measure = station["measurements"]
                    measures = []
                    measure_key = arrow.get(measure["date"], "YYYY-MM-DDTHH:mm:ss.SSSZ").int_timestamp
                    if not self.has_measure(winds_station, measure_key):
                        try:
                            new_measure = self.create_measure(
                                station=winds_station,
                                _id=measure_key,
                                wind_direction=measure["wind_heading"] or None,
                                wind_average=(
                                    Q_(measure["wind_speed_avg"], ureg.meter / ureg.second)
                                    if measure["wind_speed_avg"]
                                    else None
                                ),
                                wind_maximum=(
                                    Q_(measure["wind_speed_max"], ureg.meter / ureg.second)
                                    if measure["wind_speed_max"]
                                    else None
                                ),
                                pressure=(
                                    Pressure(measure["pressure"], qnh=None, qff=None) if measure["pressure"] else None
                                ),
                            )
                            measures.append(new_measure)
                        except ProviderException as e:
                            self.log.warning(
                                f"Error while processing measure '{measure_key}' for station '{station_id}': {e}"
                            )
                        except Exception as e:
                            self.log.exception(
                                f"Error while processing measure '{measure_key}' for station '{station_id}': {e}"
                            )
                    self.insert_measures(winds_station, measures)

                except ProviderException as e:
                    self.log.warning(f"Error while processing station '{station['id']}': {e}")
                except Exception as e:
                    self.log.exception(f"Error while processing station '{station['id']}': {e}")

        except Exception as e:
            self.log.exception(f"Error while processing MyExample: {e}")

        self.log.info("...Done !")


def openwindmap():
    OpenWindMap().process_data()


if __name__ == "__main__":
    openwindmap()
