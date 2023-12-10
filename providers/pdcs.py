import requests

from winds_mobi_provider import Pressure, Provider, ProviderException, StationNames, StationStatus


class Pdcs(Provider):
    provider_code = "pdcs"
    provider_name = "pdcs.ch"
    provider_url = "https://www.pdcs.ch/fluggebiet/wasserscheide/"

    def process_data(self):
        station_id = "unknown"
        try:
            self.log.info("Processing Pdcs data...")
            pdcs_data = requests.get(
                "https://ws.lubu.ch/ws/data.php?minutes=20", timeout=(self.connect_timeout, self.read_timeout)
            ).json()

            for pdcs_station in pdcs_data["stations"]:
                try:
                    station = self.save_station(
                        pdcs_station["id"],
                        StationNames(pdcs_station["shortName"], pdcs_station["name"]),
                        pdcs_station["coords"]["lat"],
                        pdcs_station["coords"]["lon"],
                        StationStatus.GREEN,
                        altitude=pdcs_station["altitude"],
                    )
                    station_id = station["_id"]

                    if pdcs_station["measurement"]:
                        measure = pdcs_station["measurement"][0]
                        key = measure["time"]

                        measures_collection = self.measures_collection(station_id)
                        new_measures = []

                        if not self.has_measure(measures_collection, key):
                            measure = self.create_measure(
                                station,
                                key,
                                measure["w-dir"],
                                measure["w-avg"],
                                measure["w-max"],
                                pressure=Pressure(qfe=measure["pres"]["qfe"], qnh=None, qff=None),
                            )
                            new_measures.append(measure)
                            self.insert_new_measures(measures_collection, station, new_measures)

                except ProviderException as e:
                    self.log.warning(f"Error while processing station '{station_id}': {e}")
                except Exception as e:
                    self.log.exception(f"Error while processing station '{station_id}': {e}")

        except Exception as e:
            self.log.exception(f"Error while processing Pdcs: {e}")

        self.log.info("Done !")


def pdcs():
    Pdcs().process_data()


if __name__ == "__main__":
    pdcs()
