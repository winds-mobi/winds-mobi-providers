import re

import arrow
import requests

from settings import GRAFCAN_API_KEY
from winds_mobi_provider import Q_, Pressure, Provider, ProviderException, StationNames, StationStatus, ureg


class Grafcan(Provider):
    """Provider for Grafcan weather stations in the Canary Islands.

    Data source: https://sensores.grafcan.es
    API: SensorThings API v1.0
    """

    provider_code = "grafcan"
    provider_name = "grafcan.es"
    provider_url = "https://sensores.grafcan.es"

    def __init__(self, api_key):
        super().__init__()
        if not api_key:
            raise ProviderException("GRAFCAN_API_KEY is required")
        self.api_key = api_key
        self.headers = {"Authorization": f"Api-Key {api_key}"}

    def fetch_all_things(self):
        """Fetch all stations with pagination support."""
        things = []
        url = f"{self.provider_url}/api/v1.0/things/"
        max_pages = 100
        page_count = 0

        while url and page_count < max_pages:
            try:
                response = requests.get(url, headers=self.headers, timeout=(self.connect_timeout, self.read_timeout))
                response.raise_for_status()
            except requests.exceptions.HTTPError as e:
                self.log.error(f"HTTP error fetching things: {e}, Response: {response.text[:500]}")
                raise
            data = response.json()
            things.extend(data["results"])
            url = data.get("next")
            page_count += 1

        if page_count >= max_pages:
            self.log.warning(f"Hit pagination limit of {max_pages} pages")

        return things

    def fetch_location(self, location_url):
        """Fetch location details for a station."""
        try:
            response = requests.get(
                location_url, headers=self.headers, timeout=(self.connect_timeout, self.read_timeout)
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            self.log.error(f"HTTP error fetching location: {e}, Response: {response.text[:500]}")
            raise

    def fetch_last_observations(self, thing_id):
        """Fetch the last observations for all datastreams of a station."""
        url = f"{self.provider_url}/api/v1.0/observations_last/?thing={thing_id}"
        try:
            response = requests.get(url, headers=self.headers, timeout=(self.connect_timeout, self.read_timeout))
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            self.log.error(f"HTTP error fetching observations: {e}, Response: {response.text[:500]}")
            raise

    def process_data(self):
        try:
            self.log.info("Processing Grafcan data...")

            things = self.fetch_all_things()
            self.log.info(f"Found {len(things)} stations")

            for thing in things:
                station_id = None
                try:
                    thing_id = thing["id"]
                    thing_name = thing["name"]

                    if not thing.get("location_set") or len(thing["location_set"]) == 0:
                        raise ProviderException(f"No location for station '{thing_name}'")

                    location = self.fetch_location(thing["location_set"][0])
                    coordinates = location.get("location", {}).get("coordinates")
                    if not coordinates or len(coordinates) < 2:
                        raise ProviderException(f"Invalid coordinates for station '{thing_name}'")
                    longitude = float(coordinates[0])
                    latitude = float(coordinates[1])

                    if not (-180 <= longitude <= 180) or not (-90 <= latitude <= 90):
                        raise ProviderException(f"Invalid lat/lon ({latitude}, {longitude}) for station '{thing_name}'")

                    altitude = 1
                    location_name_full = location.get("name", "")

                    altitude_match = re.search(r"\((\d+(?:\.\d+)?)\s*m(?:eters)?\)", location_name_full, re.IGNORECASE)
                    if altitude_match:
                        try:
                            altitude = float(altitude_match.group(1))
                            if not (-500 <= altitude <= 9000):
                                self.log.warning(f"Suspicious altitude {altitude}m for '{thing_name}', using default")
                                altitude = 1
                            location_name_full = re.sub(
                                r"\s*\(\d+(?:\.\d+)?\s*m(?:eters)?\)", "", location_name_full, flags=re.IGNORECASE
                            ).strip()
                        except (ValueError, IndexError) as e:
                            self.log.debug(f"Failed to parse altitude from '{location_name_full}': {e}")
                            altitude = thing.get("properties", {}).get("anemometer_height", 1) or 1

                    if "," in location_name_full:
                        location_name = location_name_full.split(",")[-1].strip()
                    else:
                        location_name = location_name_full

                    if not location_name:
                        location_name = thing_name

                    obs_data = self.fetch_last_observations(thing_id)

                    if obs_data["count"] == 0:
                        self.log.debug(f"No observations for station '{thing_name}'")
                        continue

                    observations = {obs["name"]: obs for obs in obs_data["observations"]}

                    if "Wind speed (avg.)" not in observations or "Wind direction (avg.)" not in observations:
                        self.log.debug(f"Station '{thing_name}' has no wind data, skipping")
                        continue

                    result_time = observations["Wind speed (avg.)"].get("resultTime")
                    if not result_time:
                        raise ProviderException(f"Missing resultTime for station '{thing_name}'")

                    try:
                        measurement_date = arrow.get(result_time)
                    except (arrow.parser.ParserError, ValueError) as e:
                        raise ProviderException(f"Invalid timestamp '{result_time}' for station '{thing_name}'") from e

                    age_hours = (arrow.utcnow() - measurement_date).total_seconds() / 3600

                    if age_hours < -1:
                        self.log.warning(f"Station '{thing_name}' has future timestamp: {measurement_date}")
                        status = StationStatus.ORANGE
                    elif age_hours < 1:
                        status = StationStatus.GREEN
                    elif age_hours < 24:
                        status = StationStatus.ORANGE
                    else:
                        status = StationStatus.RED

                    station = self.save_station(
                        thing_id,
                        StationNames(short_name=thing_name, name=location_name or thing_name),
                        latitude,
                        longitude,
                        status,
                        altitude=altitude,
                        url=f"{self.provider_url}/api/v1.0/things/{thing_id}/",
                    )
                    station_id = station["_id"]

                    key = measurement_date.int_timestamp
                    if not self.has_measure(station, key):
                        wind_direction_value = observations["Wind direction (avg.)"].get("value")
                        wind_avg_value = observations["Wind speed (avg.)"].get("value")

                        if wind_direction_value is None or wind_avg_value is None:
                            self.log.debug(f"Station '{thing_name}' has null wind data, skipping measurement")
                            continue

                        try:
                            wind_direction = float(wind_direction_value)
                            if not (0 <= wind_direction <= 360):
                                self.log.warning(f"Invalid wind direction {wind_direction}° for '{thing_name}'")
                                wind_direction = wind_direction % 360
                        except (TypeError, ValueError) as e:
                            raise ProviderException(
                                f"Non-numeric wind direction '{wind_direction_value}' for station '{thing_name}'"
                            ) from e

                        wind_average = Q_(float(wind_avg_value), ureg.meter / ureg.second)

                        wind_maximum = None
                        if "Wind speed (max.)" in observations:
                            wind_max_value = observations["Wind speed (max.)"].get("value")
                            if wind_max_value is not None:
                                wind_maximum = Q_(float(wind_max_value), ureg.meter / ureg.second)

                        temperature = None
                        if "Air temperature (avg.)" in observations:
                            temp_value = observations["Air temperature (avg.)"].get("value")
                            if temp_value is not None:
                                temperature = Q_(float(temp_value), ureg.degC)

                        humidity = None
                        if "Relative humidity (avg.)" in observations:
                            hum_value = observations["Relative humidity (avg.)"].get("value")
                            if hum_value is not None:
                                humidity = float(hum_value)

                        pressure = None
                        if "Atmosferic pressure (avg.)" in observations:
                            pressure_val = observations["Atmosferic pressure (avg.)"].get("value")
                            if pressure_val is not None:
                                pressure_value = Q_(float(pressure_val), ureg.millibar)
                                pressure = Pressure(qfe=pressure_value, qnh=None, qff=None)

                        rain = None
                        if "Rain (partial accumulated)" in observations:
                            rain_value = observations["Rain (partial accumulated)"].get("value")
                            if rain_value is not None:
                                rain = Q_(float(rain_value), ureg.liter / (ureg.meter**2))

                        measure = self.create_measure(
                            station,
                            key,
                            wind_direction,
                            wind_average,
                            wind_maximum,
                            temperature=temperature,
                            humidity=humidity,
                            pressure=pressure,
                            rain=rain,
                        )
                        self.insert_measures(station, measure)

                except ProviderException as e:
                    self.log.warning(f"Error while processing station '{station_id or thing.get('id')}': {e}")
                except Exception as e:
                    self.log.exception(f"Error while processing station '{station_id or thing.get('id')}': {e}")

        except Exception as e:
            self.log.exception(f"Error while processing Grafcan: {e}")

        self.log.info("...Done!")


def grafcan():
    Grafcan(GRAFCAN_API_KEY).process_data()


if __name__ == "__main__":
    grafcan()
