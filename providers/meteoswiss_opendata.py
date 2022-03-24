import arrow
import requests
from pyproj import CRS, Transformer

from winds_mobi_provider import Provider, StationStatus, ProviderException, ureg, Q_, Pressure


class MeteoSwiss(Provider):
    provider_code = "meteoswiss"
    provider_name = "meteoswiss.ch"
    provider_url = "https://www.meteoswiss.admin.ch"

    provider_urls = {
        "default": "https://www.meteoswiss.admin.ch" "/home/measurement-values.html?param={param}&station={id}",
        "en": "https://www.meteoswiss.admin.ch" "/home/measurement-values.html?param={param}&station={id}",
        "de": "https://www.meteoschweiz.admin.ch" "/home/messwerte.html?param={param}&station={id}",
        "fr": "https://www.meteosuisse.admin.ch" "/home/valeurs-mesurees.html?param={param}&station={id}",
        "it": "https://www.meteosvizzera.admin.ch" "/home/valori-attuali.html?param={param}&station={id}",
    }

    def __init__(self):
        super().__init__()

        lv95 = CRS.from_epsg(2056)
        wgs84 = CRS.from_epsg(4326)
        self.lv85_to_wgs84 = Transformer.from_crs(lv95, wgs84)

    def to_dict(self, features):
        return {feature["id"]: feature for feature in features}

    def fix_unit(self, unit):
        return unit.replace("/h", "/hour")

    def get_value(self, properties, unit=None):
        if "value" in properties:
            if not unit:
                unit = self.fix_unit(properties["unit"])
            return Q_(properties["value"], unit)
        return None

    def get_pressure_value(self, pressure_data, meteoswiss_id):
        try:
            return self.get_value(pressure_data[meteoswiss_id]["properties"])
        except KeyError:
            return None

    def process_data(self):
        try:
            self.log.info("Processing MeteoSwiss data...")

            url_pattern = (
                "https://data.geo.admin.ch/ch.meteoschweiz.messwerte-{parameter}/"
                "ch.meteoschweiz.messwerte-{parameter}_en.json"
            )

            main_wind = requests.get(
                url_pattern.format(parameter="windgeschwindigkeit-kmh-10min"),
                timeout=(self.connect_timeout, self.read_timeout),
            ).json()
            wind_gust = requests.get(
                url_pattern.format(parameter="wind-boeenspitze-kmh-10min"),
                timeout=(self.connect_timeout, self.read_timeout),
            ).json()
            temperature = requests.get(
                url_pattern.format(parameter="lufttemperatur-10min"), timeout=(self.connect_timeout, self.read_timeout)
            ).json()
            humidity = requests.get(
                url_pattern.format(parameter="luftfeuchtigkeit-10min"),
                timeout=(self.connect_timeout, self.read_timeout),
            ).json()
            pressure_qfe = requests.get(
                url_pattern.format(parameter="luftdruck-qfe-10min"), timeout=(self.connect_timeout, self.read_timeout)
            ).json()
            pressure_qnh = requests.get(
                url_pattern.format(parameter="luftdruck-qnh-10min"), timeout=(self.connect_timeout, self.read_timeout)
            ).json()
            pressure_qff = requests.get(
                url_pattern.format(parameter="luftdruck-qff-10min"), timeout=(self.connect_timeout, self.read_timeout)
            ).json()
            rain = requests.get(
                url_pattern.format(parameter="niederschlag-10min"), timeout=(self.connect_timeout, self.read_timeout)
            ).json()

            if (
                main_wind["creation_time"]
                != wind_gust["creation_time"]
                != temperature["creation_time"]
                != humidity["creation_time"]
                != pressure_qfe["creation_time"]
                != pressure_qnh["creation_time"]
                != pressure_qff["creation_time"]
                != rain["creation_time"]
            ):
                self.log.error("Creation time of parameters files are not the same")

            main_wind_data = main_wind["features"]
            wind_gust_data = self.to_dict(wind_gust["features"])
            temperature_data = self.to_dict(temperature["features"])
            humidity_data = self.to_dict(humidity["features"])
            pressure_qfe_data = self.to_dict(pressure_qfe["features"])
            pressure_qnh_data = self.to_dict(pressure_qnh["features"])
            pressure_qff_data = self.to_dict(pressure_qff["features"])
            rain_data = self.to_dict(rain["features"])

            station_id = None
            for meteoswiss_station in main_wind_data:
                try:
                    meteoswiss_id = meteoswiss_station["id"]
                    location = meteoswiss_station["geometry"]["coordinates"]
                    urls = {
                        lang: url.format(param="messwerte-windgeschwindigkeit-kmh-10min", id=meteoswiss_id)
                        for lang, url in self.provider_urls.items()
                    }

                    lat, lon = self.lv85_to_wgs84.transform(location[0], location[1])

                    station = self.save_station(
                        meteoswiss_id,
                        meteoswiss_station["properties"]["station_name"],
                        meteoswiss_station["properties"]["station_name"],
                        lat,
                        lon,
                        StationStatus.GREEN,
                        altitude=meteoswiss_station["properties"]["altitude"],
                        tz="Europe/Zurich",
                        url=urls,
                    )
                    station_id = station["_id"]

                    timestamp = meteoswiss_station["properties"].get("reference_ts", None)
                    if not timestamp or timestamp == "-":
                        self.log.warning(f"'{station_id}' has no timestamp field")
                        continue
                    key = arrow.get(
                        meteoswiss_station["properties"]["reference_ts"], "YYYY-MM-DDTHH:mm:ssZ"
                    ).int_timestamp

                    measures_collection = self.measures_collection(station_id)
                    new_measures = []

                    if meteoswiss_id in temperature_data:
                        temperature = self.get_value(temperature_data[meteoswiss_id]["properties"], unit=ureg.degC)
                    else:
                        temperature = None

                    if meteoswiss_id in humidity_data:
                        humidity = humidity_data[meteoswiss_id]["properties"]["value"]
                    else:
                        humidity = None

                    if meteoswiss_id in pressure_qfe_data:
                        pressure = Pressure(
                            qfe=self.get_pressure_value(pressure_qfe_data, meteoswiss_id),
                            qnh=self.get_pressure_value(pressure_qnh_data, meteoswiss_id),
                            qff=self.get_pressure_value(pressure_qff_data, meteoswiss_id),
                        )
                    else:
                        pressure = None

                    if meteoswiss_id in rain_data:
                        # 1mm = 1 liter/m^2
                        rain = self.get_value(
                            rain_data[meteoswiss_id]["properties"], unit=ureg.liter / (ureg.meter**2)
                        )
                    else:
                        rain = None

                    if not self.has_measure(measures_collection, key):
                        measure = self.create_measure(
                            station,
                            key,
                            meteoswiss_station["properties"]["wind_direction"],
                            self.get_value(meteoswiss_station["properties"]),
                            self.get_value(wind_gust_data[meteoswiss_id]["properties"]),
                            temperature=temperature,
                            humidity=humidity,
                            pressure=pressure,
                            rain=rain,
                        )
                        new_measures.append(measure)

                    self.insert_new_measures(measures_collection, station, new_measures)

                except ProviderException as e:
                    self.log.warning(f"Error while processing station '{station_id}': {e}")
                except Exception as e:
                    self.log.exception(f"Error while processing station '{station_id}': {e}")

        except Exception as e:
            self.log.exception(f"Error while processing MeteoSwiss: {e}")

        self.log.info("...Done!")


def meteoswiss():
    MeteoSwiss().process_data()


if __name__ == "__main__":
    meteoswiss()
