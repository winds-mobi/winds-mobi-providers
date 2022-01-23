import re

import arrow
import requests
from dateutil import tz
from lxml import etree as ET

from winds_mobi_provider import Provider, StationStatus, ProviderException

oberwallis_tz = tz.gettz("Europe/Zurich")


class FluggruppeAletsch(Provider):
    provider_code = "aletsch"
    provider_name = "fluggruppe-aletsch.ch"
    provider_url = "https://fluggruppe-aletsch.ch"

    url = "https://meteo-oberwallis.ch/wetter/{}/daten.xml"

    stations = [
        ["ried-brig", "ried-brig/XML"],
        ["blitzingu", "blitzingu/XML"],
        ["bellwald", "bellwald/XML"],
        ["fieschertal", "fiesch/XML"],
        ["chaeserstatt", "chaeserstatt/XML"],
        ["jeizinen", "jeizinen/XML"],
    ]

    def process_data(self):
        self.log.info("Processing Fluggruppe Aletsch Data...")
        for fga_id, fga_path in self.stations:
            try:
                response = requests.get(self.url.format(fga_path), timeout=(self.connect_timeout, self.read_timeout))
                parser = FgaStationParser(response.text)

                station = self.save_station(
                    fga_id,
                    parser.name(),
                    parser.name(),
                    parser.latitude(),
                    parser.longitude(),
                    StationStatus.GREEN,
                    altitude=parser.elevation(),
                )

                key = parser.key()
                if not self.has_measure(station["_id"], key):
                    try:
                        measure = self.create_measure(
                            station,
                            key,
                            parser.direction(),
                            parser.speed(),
                            parser.speed_max(),
                            rain=parser.rain(),
                            temperature=parser.temperature(),
                            humidity=parser.humidity(),
                        )

                        self.insert_new_measures(station["_id"], station, [measure])
                    except ProviderException as e:
                        self.log.warning(f"Error while processing measure '{key}' for station '{fga_id}': {e}")
                    except Exception as e:
                        self.log.exception(f"Error while processing measure '{key}' for station '{fga_id}': {e}")

            except ProviderException as e:
                self.log.warning(f"Error while processing station '{fga_id}': {e}")
            except Exception as e:
                self.log.exception(f"Error while processing station '{fga_id}': {e}")

        self.log.info("...Done Type1 via Meteo Oberwallis!")

    stations_type_2 = [
        ["rothorli", "rothorli", "Visperterminen Rothorn", "7.938", "46.2497"],
        ["klaena", "klaena", "Rosswald Klaena", "8.0632", "46.3135"],
    ]

    def process_data2(self):
        self.log.info("Processing Fluggruppe Aletsch Data Type 2...")
        for fga_id, fga_path, fga_desc, fga_long, fga_lat in self.stations_type_2:
            try:
                response = requests.get(self.url.format(fga_path), timeout=(self.connect_timeout, self.read_timeout))
                parser = FgaStationParserType2(response.text)

                station = self.save_station(
                    fga_id, fga_desc, fga_desc, fga_lat, fga_long, StationStatus.GREEN, altitude=parser.elevation()
                )

                key = parser.key()
                if not self.has_measure(station["_id"], key):
                    try:
                        measure = self.create_measure(
                            station,
                            key,
                            parser.direction(),
                            parser.speed(),
                            parser.speed_max(),
                            rain=parser.rain(),
                            temperature=parser.temperature(),
                            humidity=parser.humidity(),
                        )

                        self.insert_new_measures(station["_id"], station, [measure])
                    except ProviderException as e:
                        self.log.warning(f"Error while processing measure '{key}' for station '{fga_id}': {e}")
                    except Exception as e:
                        self.log.exception(f"Error while processing measure '{key}' for station '{fga_id}': {e}")

            except ProviderException as e:
                self.log.warning(f"Error while processing station '{fga_id}': {e}")
            except Exception as e:
                self.log.exception(f"Error while processing station '{fga_id}': {e}")
        self.log.info("...Done Type2 via Meteo Oberwallis!")


class FgaStationParser:
    def __init__(self, response):
        self._fga_station = ET.fromstring(response.encode("utf-8")).find("./station")

    def name(self):
        return self._get_value("./station/station")

    def longitude(self):
        deg = self._get_value("./station/station_longitude")
        return parse_dms(deg)

    def latitude(self):
        deg = self._get_value("./station/station_latitude")
        return parse_dms(deg)

    def elevation(self):
        return self._get_value("./elevation/elevation")

    def key(self):
        time = self._get_value("./time/date_time")
        return arrow.get(time, "D.MM.YYYY H:mm:ss").replace(tzinfo=oberwallis_tz).int_timestamp

    def direction(self):
        direction = self._get_value("./wind/direction_grad")
        return direction.replace("°", "")

    def speed(self):
        return self._get_value("./wind/speed")

    def speed_max(self):
        return self._get_value("./gust/gust")

    def rain(self):
        return self._get_value("./precipitation/rain")

    def temperature(self):
        return self._get_value("./temperature/temperature")

    def humidity(self):
        return self._get_value("./humidity/humidity")

    def _get_value(self, path):
        element = self._fga_station.find(path)
        if element is None:
            return None
        return element.attrib.get("value")


class FgaStationParserType2:
    def __init__(self, response):
        self._fga_station = ET.fromstring(response.encode("utf-8")).find("./station")

    def elevation(self):
        return self._get_value("./elevation/elevation")

    def key(self):
        time = self._get_value("./time/date_time")
        return arrow.get(time, "D.MM.YYYY H:mm:ss").replace(tzinfo=oberwallis_tz).int_timestamp

    def direction(self):
        return self._get_value("./wind/direction_wind")

    def speed(self):
        return self._get_value("./wind/speed")

    def speed_max(self):
        return self._get_value("./gust/gust_1h_max")

    def rain(self):
        return self._get_value("./precipitation/rain")

    def temperature(self):
        return self._get_value("./temperature/temperature")

    def humidity(self):
        return self._get_value("./humidity/humidity")

    def _get_value(self, path):
        element = self._fga_station.find(path)
        if element is None:
            return None
        return element.attrib.get("value")


dd_pattern = re.compile(r"(\d*)°.([\d\.]*)'.([ONWS]+)")


def dms2dd(degrees, minutes, seconds, direction):
    dd = float(degrees) + float(minutes) / 60 + float(seconds) / (60 * 60)
    if direction == "W" or direction == "S":
        dd *= -1
    return dd


def parse_dms(dms):
    parts = dd_pattern.match(dms).groups()
    lat = dms2dd(parts[0], parts[1], 0, parts[2])
    return lat


def fluggruppe_aletsch():
    aletsch_provider = FluggruppeAletsch()
    aletsch_provider.process_data()
    aletsch_provider.process_data2()


if __name__ == "__main__":
    fluggruppe_aletsch()
