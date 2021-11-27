import csv
import zipfile
from io import BytesIO, TextIOWrapper

import arrow
import requests
from dateutil import tz

from settings import BORN_TO_FLY_DEVICE_ID, BORN_TO_FLY_VENDOR_ID
from winds_mobi_provider import Provider, ProviderException, StationStatus, user_agents

borntofly_tz = tz.gettz("Europe/Zurich")


class BornToFly(Provider):
    provider_code = "borntofly"
    provider_name = "borntofly.ch"
    provider_url = "http://borntofly.ch"

    wind_directions = {
        "Norden": 0,
        "Nordnordost": 1 * (360 / 16),
        "Nordost": 2 * (360 / 16),
        "Ostnordost": 3 * (360 / 16),
        "Osten": 4 * (360 / 16),
        "Ostsüdost": 5 * (360 / 16),
        "Südost": 6 * (360 / 16),
        "Südsüdost": 7 * (360 / 16),
        "Süden": 8 * (360 / 16),
        "Südsüdwest": 9 * (360 / 16),
        "Südwest": 10 * (360 / 16),
        "Westsüdwest": 11 * (360 / 16),
        "Westen": 12 * (360 / 16),
        "Westnordwest": 13 * (360 / 16),
        "Nordwest": 14 * (360 / 16),
        "Nordnordwest": 15 * (360 / 16),
    }

    app_bundle = "de.synertronixx.remotemonitor"

    def __init__(self, born_to_fly_vendor_id, born_to_fly_device_id):
        super().__init__()
        self.vendor_id = born_to_fly_vendor_id
        self.device_id = born_to_fly_device_id

    def process_data(self):
        try:
            self.log.info("Processing BornToFly data...")

            session = requests.Session()
            session.headers.update(user_agents.chrome)
            response = session.post(
                "https://measurements.mobile-alerts.eu/Home/MeasurementDetails",
                data={
                    "deviceid": self.device_id,
                    "vendorid": self.vendor_id,
                    "appbundle": self.app_bundle,
                    "command": "export",
                    "area": "week",
                    "toepoch": arrow.now().shift(days=1).int_timestamp,
                },
            )

            station = self.save_station(
                "stechelberg",
                "Stechelberg",
                None,
                46.569360,
                7.910003,
                StationStatus.GREEN,
                altitude=830,
            )
            station_id = station["_id"]

            measures_collection = self.measures_collection(station_id)
            with zipfile.ZipFile(BytesIO(response.content)) as zip_file:
                with zip_file.open(zip_file.filelist[0].filename) as csv_file:
                    reader = csv.DictReader(
                        TextIOWrapper(csv_file, "utf-8"),
                        fieldnames=("time", "wind_avg", "na", "na", "na", "wind_max", "na", "na", "na", "wind_dir"),
                        delimiter=";",
                    )
                    # Reversed without 1st row that contains field names
                    rows = list(reader)[:0:-1]
                    for row in rows:
                        key = arrow.get(row["time"], "DD.MM.YYYY HH:mm:ss").replace(tzinfo=borntofly_tz).int_timestamp
                        if not self.has_measure(measures_collection, key):
                            try:
                                measure = self.create_measure(
                                    station,
                                    key,
                                    self.wind_directions[row["wind_dir"]],
                                    row["wind_avg"].replace(",", "."),
                                    row["wind_max"].replace(",", "."),
                                )

                                self.insert_new_measures(measures_collection, station, [measure])
                            except ProviderException as e:
                                self.log.warning(
                                    f"Error while processing measure '{key}' for station '{station_id}': {e}"
                                )
                            except Exception as e:
                                self.log.exception(
                                    f"Error while processing measure '{key}' for station '{station_id}': {e}"
                                )

        except Exception as e:
            self.log.exception(f"Error while processing BornToFly: {e}")

        self.log.info("Done !")


if __name__ == "__main__":
    BornToFly(BORN_TO_FLY_VENDOR_ID, BORN_TO_FLY_DEVICE_ID).process_data()
