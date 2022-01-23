import collections
import re
from os import path

import requests
from lxml import etree

from winds_mobi_provider import Provider, ProviderException, StationStatus
from winds_mobi_provider import user_agents

Measure = collections.namedtuple("Measure", ("key", "wind_direction", "wind_average", "wind_maximum", "temperature"))


class Slf(Provider):
    provider_code = "slf"
    provider_name = "slf.ch"
    provider_url = "https://www.slf.ch"

    provider_urls = {
        "default": "https://www.slf.ch/en/avalanche-bulletin-and-snow-situation/measured-values.html#windtab",
        "en": "https://www.slf.ch/en/avalanche-bulletin-and-snow-situation/measured-values.html#windtab",
        "de": "https://www.slf.ch/de/lawinenbulletin-und-schneesituation/messwerte.html#windtab",
        "fr": "https://www.slf.ch/fr/bulletin-davalanches-et-situation-nivologique/valeurs-mesurees.html#windtab",
        "it": "https://www.slf.ch/it/bollettino-valanghe-e-situazione-nivologica/valori-di-misura.html#windtab",
    }

    description_pattern = re.compile(r"<strong>Code:</strong> ([A-Z,0-9]{4})<br/>", re.MULTILINE)
    name_pattern = re.compile(r"(.*?) ([0-9]{2,4}) m")

    def parse_data(self, line) -> Measure:
        values = line.split(";")
        return Measure(
            key=values[0],
            wind_direction=values[7],
            wind_average=values[5],
            wind_maximum=values[6],
            temperature=values[3],
        )

    def filter_wrong_measures(self, data_list):
        if not data_list:
            return []
        measures = []
        for data in data_list:
            measure = self.parse_data(data)
            if measure.key and measure.wind_direction and measure.wind_average and measure.wind_maximum:
                measures.append(measure)
        return measures

    def add_metadata_from_kml(self, kml_path, slf_metadata):
        with open(path.join(path.dirname(__file__), kml_path)) as kml_file:
            tree = etree.parse(kml_file)
        ns = {"gis": "http://www.opengis.net/kml/2.2"}

        for placemark in tree.getroot().findall(".//gis:Placemark", namespaces=ns):
            (id,) = self.description_pattern.search(placemark.find("gis:description", namespaces=ns).text).groups()
            name, _ = self.name_pattern.search(placemark.find("gis:name", namespaces=ns).text).groups()
            lon, lat, altitude = placemark.find("gis:Point/gis:coordinates", namespaces=ns).text.split(",")

            slf_metadata[id] = {
                "name": name,
                "altitude": int(altitude),
                "lat": float(lat),
                "lon": float(lon),
            }

    def process_data(self):
        try:
            self.log.info("Processing SLF data...")

            slf_metadata = {}
            self.add_metadata_from_kml("../slf/IMIS_WIND_EN.kml", slf_metadata)
            self.add_metadata_from_kml("../slf/IMIS_SNOW_EN.kml", slf_metadata)
            self.add_metadata_from_kml("../slf/IMIS_SPECIAL_EN.kml", slf_metadata)

            session = requests.Session()
            session.headers.update(user_agents.chrome)

            result = session.get(
                "https://odb.slf.ch/odb/api/v1/stations", timeout=(self.connect_timeout, self.read_timeout)
            )
            slf_stations = result.json()

            for slf_station in slf_stations:
                station_id = None
                try:
                    slf_id = slf_station["id"]
                    result = session.get(
                        f"https://odb.slf.ch/odb/api/v1/measurement?id={slf_id}",
                        timeout=(self.connect_timeout, self.read_timeout),
                    )
                    data = result.json()
                    measures = self.filter_wrong_measures(data)
                    if not measures:
                        continue

                    name, altitude = self.name_pattern.search(slf_station["name"]).groups()
                    metadata_name, lat, lon = None, None, None
                    if slf_id in slf_metadata:
                        metadata_name = slf_metadata[slf_id]["name"]
                        lat = slf_metadata[slf_id]["lat"]
                        lon = slf_metadata[slf_id]["lon"]
                        status = StationStatus.GREEN
                    else:
                        self.log.warning(f"No metadata found for station {slf_id}/{name}")
                        status = StationStatus.ORANGE

                    station = self.save_station(
                        slf_id,
                        metadata_name or name,
                        metadata_name,
                        lat,
                        lon,
                        status,
                        altitude=altitude,
                        url=self.provider_urls,
                    )
                    station_id = station["_id"]

                    new_measures = []
                    for slf_measure in measures:
                        key = int(slf_measure.key)
                        if not self.has_measure(station_id, key):
                            try:
                                measure = self.create_measure(
                                    station,
                                    key,
                                    slf_measure.wind_direction,
                                    slf_measure.wind_average,
                                    slf_measure.wind_maximum,
                                    temperature=slf_measure.temperature,
                                )
                                new_measures.append(measure)
                            except ProviderException as e:
                                self.log.warning(
                                    f"Error while processing measure '{key}' for station '{station_id}': {e}"
                                )
                            except Exception as e:
                                self.log.exception(
                                    f"Error while processing measure '{key}' for station '{station_id}': {e}"
                                )

                    self.insert_new_measures(station_id, station, new_measures)

                except ProviderException as e:
                    self.log.warning(f"Error while processing station '{station_id}': {e}")
                except Exception as e:
                    self.log.exception(f"Error while processing station '{station_id}': {e}")

        except Exception as e:
            self.log.exception(f"Error while processing SLF: {e}")

        self.log.info("Done !")


def slf():
    Slf().process_data()


if __name__ == "__main__":
    slf()
