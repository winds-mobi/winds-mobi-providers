import re

import arrow
import requests
from dateutil import tz
from lxml import etree

from winds_mobi_provider import Provider, ProviderException, StationStatus

oberwallis_tz = tz.gettz("Europe/Zurich")
dd_pattern = re.compile(r"(\d*)°.([\d.]*)'.([ONWS]+)")


def dms2dd(degrees, minutes, seconds, direction):
    dd = float(degrees) + float(minutes) / 60 + float(seconds) / (60 * 60)
    if direction == "W" or direction == "S":
        dd *= -1
    return dd


def parse_dms(dms):
    parts = dd_pattern.match(dms).groups()
    lat = dms2dd(parts[0], parts[1], 0, parts[2])
    return lat


class FgaType1StationParser:
    url_pattern = "https://meteo-oberwallis.ch/wetter/{}/daten.xml"

    def __init__(self, path):
        self.url = self.url_pattern.format(path)
        self._station = None

    def parse(self, connect_timeout, read_timeout):
        response = requests.get(self.url, timeout=(connect_timeout, read_timeout))
        self._station = etree.fromstring(response.content).find("./station")

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
        direction = self._get_value("./wind/direction_grad") or self._get_value("./wind/direction_wind")
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
        element = self._station.find(path)
        if element is None:
            return None
        return element.attrib.get("value")


class FgaType2StationParser:
    url_pattern = "https://meteo-oberwallis.ch/wetter/{}/daten.xml"

    def __init__(self, path, name, lon, lat):
        self.url = self.url_pattern.format(path)
        self.station_name = name
        self.lon = lon
        self.lat = lat
        self._station = None

    def parse(self, connect_timeout, read_timeout):
        response = requests.get(self.url, timeout=(connect_timeout, read_timeout))
        self._station = etree.fromstring(response.content).find("./station")

    def name(self):
        return self.station_name

    def longitude(self):
        return self.lon

    def latitude(self):
        return self.lat

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
        element = self._station.find(path)
        if element is None:
            return None
        return element.attrib.get("value")


class LorawistaParser:
    url_pattern = "http://www.lorawista.ch/data/{}.xml"  # This URL is protected by an IPs whitelisting

    def __init__(self, path):
        self.url = self.url_pattern.format(path)
        self._station = None

    def parse(self, connect_timeout, read_timeout):
        response = requests.get(self.url, timeout=(connect_timeout, read_timeout))
        self._station = etree.fromstring(response.content)

    def name(self):
        return self._station.findtext("stationname")

    def longitude(self):
        return self._station.findtext("stationlongitude")

    def latitude(self):
        return self._station.findtext("stationlatitude")

    def elevation(self):
        return self._station.findtext("elevation")

    def key(self):
        time = self._station.findtext("timestamp")
        return arrow.get(time, "YYYY-MM-DTH:mm:ss.SZ").int_timestamp

    def direction(self):
        return self._station.findtext("winddir")

    def speed(self):
        return self._station.findtext("windspeed")

    def speed_max(self):
        return self._station.findtext("windmax")

    def rain(self):
        return None

    def temperature(self):
        return self._station.findtext("celcius")

    def humidity(self):
        return self._station.findtext("humid")


class FluggruppeAletsch(Provider):
    provider_code = "aletsch"
    provider_name = "fluggruppe-aletsch.ch"
    provider_url = "https://fluggruppe-aletsch.ch"

    stations = [
        ("ried-brig", FgaType1StationParser("ried-brig/XML")),
        ("blitzingu", FgaType1StationParser("blitzingu/XML")),
        ("bellwald", FgaType1StationParser("fleschen/XML")),
        ("fieschertal", FgaType1StationParser("fiesch/XML")),
        ("chaeserstatt", FgaType1StationParser("chaeserstatt/XML")),
        ("jeizinen", FgaType1StationParser("jeizinen/XML")),
        ("grimsel", FgaType1StationParser("grimselpass/XML")),
        ("hohbiel", FgaType1StationParser("hohbiel/XML")),
        ("rothorli", FgaType2StationParser("rothorli", "Visperterminen Rothorn", "7.938", "46.2497")),
        ("klaena", FgaType2StationParser("klaena", "Rosswald Klaena", "8.0632", "46.3135")),
        ("bitsch", LorawistaParser("bitsch")),
    ]

    def process_data(self):
        self.log.info("Processing Fluggruppe Aletsch data...")
        for station_id, parser in self.stations:
            try:
                parser.parse(self.connect_timeout, self.read_timeout)

                station = self.save_station(
                    station_id,
                    parser.name(),
                    parser.name(),
                    parser.latitude(),
                    parser.longitude(),
                    StationStatus.GREEN,
                    altitude=parser.elevation(),
                )

                measures_collection = self.measures_collection(station["_id"])
                key = parser.key()
                if not self.has_measure(measures_collection, key):
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

                        self.insert_new_measures(measures_collection, station, [measure])
                    except ProviderException as e:
                        self.log.warning(f"Error while processing measure '{key}' for station '{station_id}': {e}")
                    except Exception as e:
                        self.log.exception(f"Error while processing measure '{key}' for station '{station_id}': {e}")

            except ProviderException as e:
                self.log.warning(f"Error while processing station '{station_id}': {e}")
            except Exception as e:
                self.log.exception(f"Error while processing station '{station_id}': {e}")

        self.log.info("Done !")


def fluggruppe_aletsch():
    aletsch_provider = FluggruppeAletsch()
    aletsch_provider.process_data()


if __name__ == "__main__":
    fluggruppe_aletsch()
