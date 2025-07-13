import requests
from lxml import etree

from settings import IWEATHAR_KEY
from winds_mobi_provider import Q_, Pressure, Provider, ProviderException, StationNames, StationStatus, ureg


def get_attr(element, attr_name, default=...):
    attr = element.xpath(attr_name)
    if attr and attr[0].text:
        return attr[0].text
    if default is not ...:
        return default
    raise ProviderException(f"No '{attr_name}' attribute found")


class IWeathar(Provider):
    provider_code = "iweathar"
    provider_name = "iweathar.co.za"
    provider_url = "https://iweathar.co.za"

    def __init__(self, iweathar_key):
        super().__init__()
        self.iweathar_key = iweathar_key

    def process_data(self):
        try:
            self.log.info("Processing iWeathar data...")

            result_tree = etree.parse(
                requests.get(
                    f"https://iweathar.co.za/live_data.php?unit=kmh&key={self.iweathar_key}",
                    stream=True,
                    timeout=(self.connect_timeout, self.read_timeout),
                ).raw
            )

            for item in result_tree.xpath("//ITEM"):
                iweathar_id = None
                station_id = None
                try:
                    iweathar_id = get_attr(item, "STATION_ID")
                    name = get_attr(item, "LOCATION")
                    status_attr = get_attr(item, "STATUS")
                    if status_attr == "ON-LINE":
                        status = StationStatus.GREEN
                    elif status_attr == "OFF-LINE":
                        status = StationStatus.RED
                    else:
                        raise ProviderException(f"Invalid status '{status_attr}'")

                    lat, lon = get_attr(item, "LAT"), get_attr(item, "LONG")
                    if lat == "0" and lon == "0":
                        # iWeathar has a lot of stations with lat=0 and lon=0
                        self.log.warning(f"Station '{iweathar_id}' has invalid latitude '{lat}' and longitude '{lon}'")
                        continue

                    station = self.save_station(
                        iweathar_id,
                        lambda names: StationNames(short_name=name, name=names.name or name),
                        lat,
                        lon,
                        status,
                        url=f"{self.provider_url}/display?s_id={iweathar_id}",
                    )
                    station_id = station["_id"]

                    if status == StationStatus.GREEN:
                        key = int(get_attr(item, "UNIX_DATE_STAMP"))
                        if not self.has_measure(station, key):
                            try:
                                wind_dir_attr = get_attr(item, "WIND_ANG")
                                wind_dir = Q_(int(wind_dir_attr), ureg.degree)

                                wind_avg_attr = get_attr(item, "WIND_AVG")
                                wind_avg = Q_(float(wind_avg_attr), ureg.km / ureg.hour)

                                wind_max_attr = get_attr(item, "WIND_MAX")
                                wind_max = Q_(float(wind_max_attr), ureg.km / ureg.hour)

                                temp_attr = get_attr(item, "TEMPERATURE_C", None)
                                temp = Q_(float(temp_attr), ureg.degC) if temp_attr else None

                                humidity_attr = get_attr(item, "HUMIDITY_PERC", None)
                                humidity = float(humidity_attr) if humidity_attr else None

                                pressure_attr = get_attr(item, "PRESSURE_MB", None)
                                pressure = Q_(float(pressure_attr), ureg.hPa) if pressure_attr else None

                                rain_attr = get_attr(item, "RAINFALL_MM", None)
                                rain = Q_(rain_attr, ureg.liter / (ureg.meter**2)) if rain_attr else None

                                measure = self.create_measure(
                                    station,
                                    key,
                                    wind_dir,
                                    wind_avg,
                                    wind_max,
                                    temperature=temp,
                                    humidity=humidity,
                                    pressure=Pressure(qfe=pressure, qnh=None, qff=None),
                                    rain=rain,
                                )
                                self.insert_measures(station, measure)
                            except ProviderException as e:
                                self.log.warning(
                                    f"Error while processing measure '{key}' for station '{station_id}': {e}"
                                )
                            except Exception as e:
                                self.log.exception(
                                    f"Error while processing measure '{key}' for station '{station_id}': {e}"
                                )

                except ProviderException as e:
                    self.log.warning(f"Error while processing station '{station_id or iweathar_id}': {e}")
                except Exception as e:
                    self.log.exception(f"Error while processing station '{station_id or iweathar_id}': {e}")

        except Exception as e:
            self.log.exception(f"Error while processing iWeathar: {e}")

        self.log.info("...Done!")


def iweathar():
    IWeathar(IWEATHAR_KEY).process_data()


if __name__ == "__main__":
    iweathar()
