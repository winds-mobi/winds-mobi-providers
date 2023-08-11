import json

import arrow
import requests
from dateutil import tz

from settings import FFVL_API_KEY
from winds_mobi_provider import Pressure, Provider, ProviderException, StationStatus


class Ffvl(Provider):
    provider_code = "ffvl"
    provider_name = "ffvl.fr"
    provider_url = "https://www.balisemeteo.com"

    def __init__(self, ffvl_api_key):
        super().__init__()
        self.ffvl_api_key = ffvl_api_key

    def process_data(self):
        stations = {}
        try:
            self.log.info("Processing FFVL data...")

            result = requests.get(
                f"https://data.ffvl.fr/api/?base=balises&r=list&mode=json&key={self.ffvl_api_key}",
                timeout=(self.connect_timeout, self.read_timeout),
            )
            # TODO: remove the BOM encoding when the FFVL will fix the forbidden json encoding on their side
            # https://www.rfc-editor.org/rfc/rfc7159#section-8.1
            ffvl_stations = json.loads(result.content.decode("utf-8-sig"))

            for ffvl_station in ffvl_stations:
                ffvl_id = None
                try:
                    type = ffvl_station.get("station_type", "").lower()
                    if type not in ["holfuy", "pioupiou", "iweathar"]:
                        ffvl_id = ffvl_station["idBalise"]
                        station = self.save_station(
                            ffvl_id,
                            ffvl_station["nom"],
                            ffvl_station["nom"],
                            ffvl_station["latitude"],
                            ffvl_station["longitude"],
                            StationStatus.GREEN,
                            altitude=ffvl_station["altitude"],
                            url=ffvl_station["url"],
                        )
                        stations[station["_id"]] = station

                except ProviderException as e:
                    self.log.warning(f"Error while processing station '{ffvl_id}': {e}")
                except Exception as e:
                    self.log.exception(f"Error while processing station '{ffvl_id}': {e}")

        except ProviderException as e:
            self.log.warning(f"Error while processing stations: {e}")
        except Exception as e:
            self.log.exception(f"Error while processing stations: {e}")

        try:
            result = requests.get(
                f"https://data.ffvl.fr/api/?base=balises&r=releves_meteo&key={self.ffvl_api_key}",
                timeout=(self.connect_timeout, self.read_timeout),
            )
            # TODO: remove the BOM encoding when the FFVL will fix the forbidden json encoding on their side
            # https://www.rfc-editor.org/rfc/rfc7159#section-8.1
            ffvl_measures = json.loads(result.content.decode("utf-8-sig"))

            ffvl_tz = tz.gettz("Europe/Paris")
            for ffvl_measure in ffvl_measures:
                station_id = None
                try:
                    ffvl_id = ffvl_measure["idbalise"]
                    station_id = self.get_station_id(ffvl_id)
                    if station_id not in stations:
                        raise ProviderException(f"Unknown station '{station_id}'")
                    station = stations[station_id]

                    measures_collection = self.measures_collection(station_id)
                    key = arrow.get(ffvl_measure["date"], "YYYY-MM-DD HH:mm:ss").replace(tzinfo=ffvl_tz).int_timestamp

                    if not self.has_measure(measures_collection, key):
                        measure = self.create_measure(
                            station,
                            key,
                            ffvl_measure["directVentMoy"],
                            ffvl_measure["vitesseVentMoy"],
                            ffvl_measure["vitesseVentMax"],
                            temperature=ffvl_measure["temperature"],
                            humidity=ffvl_measure["hydrometrie"],
                            pressure=Pressure(qfe=ffvl_measure["pression"], qnh=None, qff=None),
                        )
                        self.insert_new_measures(measures_collection, station, [measure])

                except ProviderException as e:
                    self.log.warning(f"Error while processing measures for station '{station_id}': {e}")
                except Exception as e:
                    self.log.exception(f"Error while processing measures for station '{station_id}': {e}")

        except ProviderException as e:
            self.log.warning(f"Error while processing FFVL: {e}")
        except Exception as e:
            self.log.exception(f"Error while processing FFVL: {e}")

        self.log.info("...Done!")


def ffvl():
    Ffvl(FFVL_API_KEY).process_data()


if __name__ == "__main__":
    ffvl()
