import requests

from winds_mobi_provider import Q_, Provider, ProviderException, StationNames, StationStatus, ureg


class Burnair(Provider):
    provider_code = "burnair"
    provider_name = "burnair.ch"
    provider_url = "https://www.burnair.ch"

    def process_data(self):
        self.log.info("Processing burnair data...")
        try:
            # Public feed, licensed under CC BY 4.0: see the "license" key of the file. A station is only listed while
            # it has a measure from the last hour, and "historic" holds that hour, newest first.
            data = requests.get(
                "https://static.burnair.cloud/meteo/burnair-stations.json",
                timeout=(self.connect_timeout, self.read_timeout),
            ).json()
            for station in data["stations"]:
                try:
                    longitude, latitude = station["loc"]["coordinates"]
                    winds_station = self.save_station(
                        provider_id=station["pv-id"],
                        # Let winds.mobi provide the full name (if found) with the help of Google Geocoding API
                        names=lambda names: StationNames(
                            short_name=station["short"], name=names.name or station["name"]
                        ),
                        latitude=latitude,
                        longitude=longitude,
                        status=StationStatus(station["status"]),
                        altitude=station.get("alt"),
                    )
                    station_id = winds_station["_id"]

                    measures = []
                    for measure in reversed(station["historic"]):
                        measure_key = measure["_id"]
                        if not self.has_measure(winds_station, measure_key):
                            try:
                                measures.append(
                                    self.create_measure(
                                        station=winds_station,
                                        _id=measure_key,
                                        wind_direction=measure["w-dir"],
                                        wind_average=Q_(measure["w-avg"], ureg.kilometer / ureg.hour),
                                        wind_maximum=Q_(measure["w-max"], ureg.kilometer / ureg.hour),
                                    )
                                )
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
                    self.log.warning(f"Error while processing station '{station['_id']}': {e}")
                except Exception as e:
                    self.log.exception(f"Error while processing station '{station['_id']}': {e}")

        except Exception as e:
            self.log.exception(f"Error while processing burnair: {e}")

        self.log.info("...Done !")


def burnair():
    Burnair().process_data()


if __name__ == "__main__":
    burnair()
