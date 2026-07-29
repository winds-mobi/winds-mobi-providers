"""
CumulusMX Provider for winds.mobi

This provider extracts weather data from CumulusMX weather stations (https://cumulusmx.com).
It parses the websitedata.json file that CumulusMX 4.x instances expose and converts
the data into winds.mobi format.

To add stations, configure the CUMULUSMX_STATIONS list with:
- url: Base URL of the CumulusMX instance
- station_id: Unique identifier for the station
- short_name: Short display name
- name: Full station name
- timezone: IANA timezone string (e.g., "Europe/Zurich")
"""

import re
from zoneinfo import ZoneInfo

import arrow
import requests

from winds_mobi_provider import Q_, Pressure, Provider, ProviderException, StationNames, StationStatus, ureg

CUMULUSMX_STATIONS = [
    (
        "https://wetter.richert.ch",
        "1",
        "Bos-cha",
        "Bos-cha",
        "Europe/Zurich",
    ),
]


class CumulusMX(Provider):
    provider_code = "cumulusmx"
    provider_name = "CumulusMX"
    provider_url = "https://cumulusmx.com"

    def parse_dms_coordinate(self, dms_str):
        """Parse DMS (Degrees, Minutes, Seconds) coordinate string to decimal degrees."""
        match = re.match(r"([NSEW])\s*(\d+)[°\s]+(\d+)[\'′\s]+(\d+)", dms_str)
        if not match:
            raise ProviderException(f"Unable to parse coordinate: {dms_str}")

        direction, degrees, minutes, seconds = match.groups()
        decimal = float(degrees) + float(minutes) / 60 + float(seconds) / 3600

        if direction in ["S", "W"]:
            decimal = -decimal

        return decimal

    def process_station(self, provider_url, station_id, station_short_name, station_name, timezone):
        """Process data for a single CumulusMX station."""
        try:
            url = f"{provider_url}/cumulusmx/websitedata.json"
            response = requests.get(url, timeout=(self.connect_timeout, self.read_timeout))
            response.raise_for_status()
            data = response.json()

            if "update" not in data:
                raise ProviderException("Missing 'update' field in websitedata.json")

            datetime_str = data["update"]
            measure_time = arrow.get(datetime_str, "DD.MM.YYYY HH:mm:ss", tzinfo=timezone)

            if "temp" not in data:
                raise ProviderException("Missing 'temp' field in websitedata.json")
            temperature = float(data["temp"])
            humidity = float(data.get("hum")) if "hum" in data else None
            wind_avg = float(data.get("wspeed", 0))
            wind_gust = float(data.get("wgust", 0))
            wind_bearing = float(data.get("avgbearing", 0))
            pressure = float(data.get("press")) if "press" in data else None

            temp_unit = data.get("tempunit", "°C")
            pressure_unit = data.get("pressunit", "hPa")
            wind_unit = data.get("windunit", "km/h")

            lat_str = data.get("latitude")
            lon_str = data.get("longitude")
            altitude_str = data.get("altitude")

            if not lat_str or not lon_str:
                raise ProviderException("Missing latitude or longitude in websitedata.json")

            latitude = self.parse_dms_coordinate(lat_str)
            longitude = self.parse_dms_coordinate(lon_str)

            altitude = None
            if altitude_str:
                altitude_match = re.match(r"(\d+(?:\.\d+)?)\s*(\w+)", altitude_str)
                if altitude_match:
                    altitude_value = float(altitude_match.group(1))
                    altitude_unit = altitude_match.group(2).lower()

                    if altitude_unit in ["ft", "feet"]:
                        altitude = int(altitude_value * 0.3048)
                    else:
                        altitude = int(altitude_value)

            winds_station = self.save_station(
                provider_id=station_id,
                names=StationNames(short_name=station_short_name, name=station_name),
                latitude=latitude,
                longitude=longitude,
                altitude=altitude,
                status=StationStatus.GREEN,
                url=f"{provider_url}/cumulusmx/today.htm",
            )
            station_db_id = winds_station["_id"]

            measure_key = measure_time.int_timestamp
            if not self.has_measure(winds_station, measure_key):
                try:
                    temp_unit_clean = temp_unit.replace("°", "")
                    if temp_unit_clean == "F":
                        temp_quantity = Q_(temperature, ureg.degF)
                    else:
                        temp_quantity = Q_(temperature, ureg.degC)

                    if pressure is not None:
                        if pressure_unit == "inHg":
                            pressure_quantity = Q_(pressure, ureg.inHg)
                        else:
                            pressure_quantity = Q_(pressure, ureg.hPa)
                    else:
                        pressure_quantity = None

                    wind_unit_map = {
                        "km/h": ureg.kilometer / ureg.hour,
                        "mph": ureg.mile / ureg.hour,
                        "m/s": ureg.meter / ureg.second,
                        "knots": ureg.knot,
                    }
                    wind_ureg_unit = wind_unit_map.get(wind_unit, ureg.kilometer / ureg.hour)

                    new_measure = self.create_measure(
                        station=winds_station,
                        _id=measure_key,
                        wind_direction=wind_bearing,
                        wind_average=Q_(wind_avg, wind_ureg_unit),
                        wind_maximum=Q_(wind_gust, wind_ureg_unit),
                        temperature=temp_quantity,
                        humidity=humidity,
                        pressure=Pressure(qfe=None, qnh=pressure_quantity, qff=None) if pressure_quantity else None,
                    )
                    self.insert_measures(winds_station, new_measure)
                except ProviderException as e:
                    self.log.warning(
                        f"Error while processing measure '{measure_key}' for station '{station_db_id}': {e}"
                    )
                except Exception as e:
                    self.log.exception(
                        f"Error while processing measure '{measure_key}' for station '{station_db_id}': {e}"
                    )

        except ProviderException as e:
            self.log.warning(f"Error while processing CumulusMX station '{station_id}' at {provider_url}: {e}")
        except Exception as e:
            self.log.exception(f"Error while processing CumulusMX station '{station_id}' at {provider_url}: {e}")

    def process_data(self):
        try:
            self.log.info("Processing CumulusMX stations...")

            for station_config in CUMULUSMX_STATIONS:
                provider_url, station_id, station_short_name, station_name, timezone_str = station_config
                timezone = ZoneInfo(timezone_str)

                self.log.info(f"Processing station '{station_id}' at {provider_url}")
                self.process_station(provider_url, station_id, station_short_name, station_name, timezone)

        except Exception as e:
            self.log.exception(f"Error while processing CumulusMX: {e}")

        self.log.info("Done !")


def cumulusmx():
    CumulusMX().process_data()


if __name__ == "__main__":
    cumulusmx()
