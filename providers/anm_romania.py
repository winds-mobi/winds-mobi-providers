import math
import re

import arrow
import requests

from winds_mobi_provider import Q_, Pressure, Provider, ProviderException, StationNames, StationStatus, ureg


class AnmRomania(Provider):
    provider_code = "anm_romania"
    provider_name = "ANM Romania"
    provider_url = "https://www.meteoromania.ro/"
    api_url = "https://www.meteoromania.ro/wp-json/meteoapi/v2/starea-vremii"

    DIRECTIONS = {
        "N": 0.0,
        "NNE": 22.5,
        "NE": 45.0,
        "ENE": 67.5,
        "E": 90.0,
        "ESE": 112.5,
        "SE": 135.0,
        "SSE": 157.5,
        "S": 180.0,
        "SSV": 202.5,
        "SV": 225.0,
        "VSV": 247.5,
        "V": 270.0,
        "VNV": 292.5,
        "NV": 315.0,
        "NNV": 337.5,
    }

    @staticmethod
    def web_mercator_to_wgs84(x, y):
        """Convert EPSG:3857 coordinates to WGS84 lon/lat."""
        x = float(x)
        y = float(y)
        lon = x * 180.0 / 20037508.34
        lat = math.degrees(2.0 * math.atan(math.exp(y / 6378137.0)) - math.pi / 2.0)
        return lat, lon

    @classmethod
    def parse_wind(cls, value):
        """Return (speed_m_s, direction_degrees) from e.g. '2.9 m/s, directia : V'."""
        if not value or str(value).strip().lower() == "indisponibil":
            return None, None
        m = re.search(r"([-+]?\d+(?:[.,]\d+)?)\s*m/s.*?:\s*([A-Z]+)", str(value), re.I)
        if not m:
            return None, None
        speed = float(m.group(1).replace(",", "."))
        direction = cls.DIRECTIONS.get(m.group(2).upper())
        return speed, direction

    @staticmethod
    def parse_pressure(value):
        if not value or str(value).strip().lower() == "indisponibil":
            return None
        m = re.search(r"([-+]?\d+(?:[.,]\d+)?)\s*mb", str(value), re.I)
        return float(m.group(1).replace(",", ".")) if m else None

    @staticmethod
    def parse_temperature(value):
        try:
            return float(str(value).replace(",", "."))
        except (TypeError, ValueError):
            return None

    def process_data(self):
        self.log.info("Processing ANM Romania data...")
        try:
            response = requests.get(
                self.api_url,
                timeout=(self.connect_timeout, self.read_timeout),
            )
            response.raise_for_status()
            data = response.json()

            # Top-level ANM timestamp, e.g. 2026-09-24T11:00:00+03:00
            dataset_time = arrow.get(data["date"])
            measure_key = dataset_time.int_timestamp

            for feature in data.get("features", []):
                props = feature.get("properties", {})
                geometry = feature.get("geometry", {})
                name = str(props.get("nume", "")).strip()
                coordinates = geometry.get("coordinates", [])

                if not name or len(coordinates) < 2:
                    continue

                try:
                    lat, lon = self.web_mercator_to_wgs84(coordinates[0], coordinates[1])
                    wind_speed, wind_direction = self.parse_wind(props.get("vant"))
                    temperature = self.parse_temperature(props.get("tempe"))
                    pressure = self.parse_pressure(props.get("presiunetext"))

                    if wind_speed is None or wind_direction is None:
                        continue

                    # Stable enough while ANM does not expose a station ID in this endpoint.
                    provider_id = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")

                    winds_station = self.save_station(
                        provider_id=provider_id,
                        names=StationNames(
                            short_name=name,
                            name=name,
                        ),
                        latitude=lat,
                        longitude=lon,
                        status=StationStatus.GREEN,
                        url=self.provider_url,
                    )

                    if self.has_measure(winds_station, measure_key):
                        continue

                    # This public endpoint has no gust field. Do not invent wind_maximum.
                    # winds.mobi requires wind_direction, wind_average and
                    # wind_maximum arguments. ANM does not expose gust/max wind
                    # in this endpoint, so wind_maximum must remain None.
                    #
                    # If ANM has no usable wind observation, skip the measure:
                    # winds.mobi does not accept all three mandatory wind values
                    # as None.

                    new_measure = self.create_measure(
                        station=winds_station,
                        _id=measure_key,
                        wind_direction=wind_direction,
                        wind_average=Q_(wind_speed, ureg.meter / ureg.second),
                        wind_maximum=None,
                        temperature=(Q_(temperature, ureg.degC) if temperature is not None else None),
                        pressure=(Pressure(pressure, qnh=None, qff=None) if pressure is not None else None),
                    )

                    self.insert_measures(winds_station, [new_measure])

                except ProviderException as e:
                    self.log.warning(f"Error while processing ANM station '{name}': {e}")
                except Exception as e:
                    self.log.exception(f"Error while processing ANM station '{name}': {e}")

        except Exception as e:
            self.log.exception(f"Error while processing ANM Romania: {e}")

        self.log.info("...Done !")


def anm_romania():
    AnmRomania().process_data()


if __name__ == "__main__":
    anm_romania()
