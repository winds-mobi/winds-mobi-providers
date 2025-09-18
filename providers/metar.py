import io
import json
import math
from gzip import GzipFile
from random import randint

import arrow
import arrow.parser
import requests
from lxml import etree

from winds_mobi_provider import Q_, Pressure, Provider, ProviderException, StationNames, StationStatus, ureg


def compute_humidity(dew_point: Q_, temp: Q_):
    if dew_point is None or temp is None:
        return None

    a = 17.625
    b = 243.04
    td = dew_point.to(ureg.degC).magnitude
    t = temp.to(ureg.degC).magnitude

    return 100 * (math.exp((a * td) / (b + td))) / (math.exp((a * t) / (b + t)))


def get_attr(element, attr_name, default=...):
    attr = element.xpath(attr_name)
    if attr and attr[0].text:
        return attr[0].text
    if default is not ...:
        return default
    raise ProviderException(f"No '{attr_name}' attribute found")


class Metar(Provider):
    provider_code = "metar"
    provider_name = "aviationweather.gov"
    provider_url = "https://www.aviationweather.gov"

    def process_data(self):
        try:
            self.log.info("Processing Metar data...")

            request = requests.get(
                "https://aviationweather.gov/data/cache/stations.cache.json.gz",
                timeout=(self.connect_timeout, self.read_timeout),
            )
            stations = {
                station["icaoId"]: station
                for station in json.loads(GzipFile(fileobj=io.BytesIO(request.content)).read().decode("utf-8"))
            }
            request = requests.get(
                "https://aviationweather.gov/data/cache/metars.cache.xml.gz",
                timeout=(self.connect_timeout, self.read_timeout),
            )
            metar_tree = etree.parse(GzipFile(fileobj=io.BytesIO(request.content)))

            for metar in metar_tree.xpath("//METAR"):
                metar_id = None
                station_id = None
                try:
                    metar_id = get_attr(metar, "station_id")
                    station = stations.get(metar_id)
                    if not station:
                        self.log.warning(f"Unable to find icao '{metar_id}' in stations.cache.json")
                        continue

                    def get_station_names(names: StationNames) -> StationNames:
                        short_name = station["site"]
                        name = names.name or station["site"]
                        if len(short_name) > len(name):
                            # Swap short_name and name
                            short_name, name = name, short_name
                        return StationNames(short_name, name)

                    station = self.save_station(
                        metar_id,
                        get_station_names,
                        station["lat"],
                        station["lon"],
                        StationStatus.GREEN,
                        altitude=station["elev"],
                        url=f"{self.provider_url}/data/metar/?id={metar_id}&hours=0&decoded=yes&include_taf=yes",
                    )

                    station_id = station["_id"]
                    key = arrow.get(get_attr(metar, "observation_time")).int_timestamp

                    if not self.has_measure(station, key):
                        try:
                            if (
                                not metar.xpath("wind_dir_degrees")
                                and not metar.xpath("wind_speed_kt")
                                and not metar.xpath("wind_gust_kt")
                            ):
                                raise ProviderException("No wind data")

                            wind_dir_attr = get_attr(metar, "wind_dir_degrees")
                            if wind_dir_attr == "VRB":
                                # For VaRiaBle direction, use a random value
                                wind_dir = Q_(randint(0, 359), ureg.degree)
                            else:
                                wind_dir = Q_(int(wind_dir_attr), ureg.degree)

                            wind_avg_attr = get_attr(metar, "wind_speed_kt")
                            wind_avg = Q_(float(wind_avg_attr), ureg.knot)

                            wind_max_attr = get_attr(metar, "wind_gust_kt", None)
                            wind_max = Q_(float(wind_max_attr), ureg.knot) if wind_max_attr else wind_avg

                            temp_attr = get_attr(metar, "temp_c", None)
                            temp = Q_(float(temp_attr), ureg.degC) if temp_attr else None

                            dewpoint_attr = get_attr(metar, "dewpoint_c", None)
                            dewpoint = Q_(float(dewpoint_attr), ureg.degC) if dewpoint_attr else None

                            pressure_sea_attr = get_attr(metar, "sea_level_pressure_mb", None)
                            pressure_sea = Q_(float(pressure_sea_attr), ureg.hPa) if pressure_sea_attr else None

                            measure = self.create_measure(
                                station,
                                key,
                                wind_dir,
                                wind_avg,
                                wind_max,
                                temperature=temp,
                                humidity=compute_humidity(dewpoint, temp),
                                pressure=Pressure(
                                    qfe=None,
                                    qnh=None,
                                    qff=pressure_sea,
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
                    self.log.warning(f"Error while processing station '{station_id or metar_id}': {e}")
                except Exception as e:
                    self.log.exception(f"Error while processing station '{station_id or metar_id}': {e}")

        except Exception as e:
            self.log.exception(f"Error while processing Metar: {e}")

        self.log.info("...Done!")


def metar():
    Metar().process_data()


if __name__ == "__main__":
    metar()
