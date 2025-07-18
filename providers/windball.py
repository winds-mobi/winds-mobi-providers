import arrow
import requests

from winds_mobi_provider import Q_, Provider, ProviderException, StationNames, StationStatus, ureg


class Windball(Provider):
    provider_code = "windball"
    provider_name = "windball.ch"
    provider_url = "https://www.windball.ch"

    def process_data(self):
        self.log.info("Processing windball data...")
        try:
            data = requests.get(
                "https://server.windball.ch/api/windsmobi?units=kmh", timeout=(self.connect_timeout, self.read_timeout)
            ).json()
            for station in data:

                # Let winds.mobi provide the geocoding_name (if found) with the help of Google Geocoding API
                def build_station_name(geocoding_names):
                    if geocoding_names.name is None:
                        return StationNames(short_name=station["name"], name=station["name"])
                    else:
                        return StationNames(short_name=station["name"], name=geocoding_names.name)

                try:
                    if "name" in station and station["name"].startswith("Test"):
                        status = StationStatus.HIDDEN
                    elif station["status"] == "enabled":
                        status = StationStatus.GREEN
                    else:
                        status = StationStatus.HIDDEN

                    winds_station = self.save_station(
                        provider_id=station["id"],
                        # Let winds.mobi provide the full name (if found) with the help of Google Geocoding API
                        names=build_station_name,  # Pass the function here
                        latitude=station["latitude"],
                        longitude=station["longitude"],
                        status=status,
                        # If url is a dict, the keys must correspond to an ISO 639-1 language code. It also needs a
                        # "default" key, "english" if available. Here an example:
                        url={
                            "default": f"{self.provider_url}/windchart?device={station['id']}",
                        },
                    )
                    station_id = winds_station["_id"]

                    measures = []
                    for measure in station["measures"]:
                        measure_key = arrow.get(measure["time"]).int_timestamp
                        if not self.has_measure(winds_station, measure_key):
                            try:
                                measure = self.create_measure(
                                    station=winds_station,
                                    _id=measure_key,
                                    wind_direction=measure["windDirection"],
                                    wind_average=Q_(measure["windAverage"], ureg.kilometer / ureg.hour),
                                    wind_maximum=Q_(measure["windMaximum"], ureg.kilometer / ureg.hour),
                                )
                                measures.append(measure)
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
            self.log.exception(f"Error while processing windball: {e}")

        self.log.info("...Done !")


def windball():
    Windball().process_data()


if __name__ == "__main__":
    windball()
