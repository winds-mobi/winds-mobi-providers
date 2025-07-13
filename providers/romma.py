import urllib.parse
from zoneinfo import ZoneInfo

import arrow
import requests
from lxml import etree

from settings import ROMMA_KEY
from winds_mobi_provider import Pressure, Provider, ProviderException, StationNames, StationStatus


class Romma(Provider):
    provider_code = "romma"
    provider_name = "romma.fr"
    provider_url = "https://www.romma.fr"
    timezone = ZoneInfo("Europe/Paris")

    wind_directions = {
        "N": 0,
        "NNE": 1 * (360 / 16),
        "NE": 2 * (360 / 16),
        "ENE": 3 * (360 / 16),
        "E": 4 * (360 / 16),
        "ESE": 5 * (360 / 16),
        "SE": 6 * (360 / 16),
        "SSE": 7 * (360 / 16),
        "S": 8 * (360 / 16),
        "SSO": 9 * (360 / 16),
        "SO": 10 * (360 / 16),
        "OSO": 11 * (360 / 16),
        "O": 12 * (360 / 16),
        "ONO": 13 * (360 / 16),
        "NO": 14 * (360 / 16),
        "NNO": 15 * (360 / 16),
    }

    def __init__(self, romma_key):
        super().__init__()
        self.romma_key = romma_key

    def get_value(self, value):
        if value == "--" or value == "---":
            return None
        return value

    def process_data(self):
        try:
            self.log.info("Processing Romma data...")

            content = requests.get(
                f"https://www.romma.fr/releves_romma_xml.php?id={self.romma_key}",
                timeout=(self.connect_timeout, self.read_timeout),
            ).text
            result_tree = etree.fromstring(content)

            for report in result_tree.xpath("//releves/releve"):
                station_id = None
                try:
                    romma_id = report.xpath("id")[0].text
                    name = report.xpath("station")[0].text
                    status = StationStatus.GREEN if report.xpath("valide")[0].text == "1" else StationStatus.RED

                    station = self.save_station(
                        romma_id,
                        StationNames(short_name=name, name=name),
                        report.xpath("latitude")[0].text,
                        report.xpath("longitude")[0].text,
                        status,
                        altitude=report.xpath("altitude")[0].text,
                        url=urllib.parse.urljoin(self.provider_url, f"/station_24.php?id={romma_id}"),
                    )
                    station_id = station["_id"]

                    wind_dir = self.get_value(report.xpath("direction")[0].text)
                    if not wind_dir:
                        self.log.warning(f"Station '{station_id}' has no wind direction value")
                        continue

                    key = (
                        arrow.get(report.xpath("date")[0].text, "D-MM-YYYY H:mm")
                        .replace(tzinfo=self.timezone)
                        .int_timestamp
                    )
                    if not self.has_measure(station, key):
                        try:
                            measure = self.create_measure(
                                station,
                                key,
                                self.wind_directions[wind_dir],
                                self.get_value(report.xpath("vent_moyen_10")[0].text),
                                self.get_value(report.xpath("rafale_maxi")[0].text),
                                temperature=self.get_value(report.xpath("temperature")[0].text),
                                humidity=self.get_value(report.xpath("humidite")[0].text),
                                pressure=Pressure(
                                    qfe=self.get_value(report.xpath("pression")[0].text), qnh=None, qff=None
                                ),
                            )
                            self.insert_measures(station, measure)
                        except ProviderException as e:
                            self.log.warning(f"Error while processing measure '{key}' for station '{station_id}': {e}")
                        except Exception as e:
                            self.log.exception(
                                f"Error while processing measure '{key}' for station '{station_id}': {e}"
                            )

                except ProviderException as e:
                    self.log.warning(f"Error while processing station '{station_id}': {e}")
                except Exception as e:
                    self.log.exception(f"Error while processing station '{station_id}': {e}")

        except Exception as e:
            self.log.exception(f"Error while processing Romma: {e}")

        self.log.info("...Done!")


def romma():
    Romma(ROMMA_KEY).process_data()


if __name__ == "__main__":
    romma()
