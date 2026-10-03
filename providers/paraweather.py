"""ParaWeather provider for winds-mobi-providers.

Set PARAWEATHER_API_KEY and provide station coordinates via API latitude/longitude
or PARAWEATHER_COORDINATES JSON mapping station IDs to latitude/longitude.
"""
import json
import math
import os
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path
import requests

from winds_mobi_provider import Q_, Pressure, Provider, ProviderException, StationNames, StationStatus, ureg


class ParaWeather(Provider):
    provider_code = "paraweather"
    provider_name = "ParaWeather"
    provider_url = "https://www.xpander.ro"
    api_url = "https://www.xpander.ro/api/"
    max_age = 300

    def process_data(self):
        key = os.environ.get("PARAWEATHER_API_KEY")
        if not key:
            raise ProviderException("Missing PARAWEATHER_API_KEY")
        coordinates_file = Path(__file__).resolve().parent.parent / "paraweather-coordinates.json"

        if os.environ.get("PARAWEATHER_COORDINATES"):
            coordinates = json.loads(os.environ["PARAWEATHER_COORDINATES"])
        else:
            with coordinates_file.open(encoding="utf-8") as f:
                coordinates = json.load(f)

        response = requests.get(self.api_url, params={"auth": key},
                                timeout=(self.connect_timeout, self.read_timeout))
        response.raise_for_status()
        stations = response.json()["meteo"]
        if not isinstance(stations, dict):
            raise ProviderException("Invalid meteo object")

        for station_id, station in stations.items():
            try:
                self.process_station(str(station_id), station, coordinates)
            except Exception:
                self.log.exception("ParaWeather station %s failed", station_id)

    def process_station(self, station_id, station, coordinates):
        name = str(station.get("location") or f"ParaWeather {station_id}")
        if name.lower().startswith(("reserved", "rezerved")):
            return

        fallback = coordinates.get(station_id, {})
        lat = station.get("latitude", fallback.get("latitude"))
        lon = station.get("longitude", fallback.get("longitude"))
        if lat is None or lon is None:
            self.log.warning("Station %s skipped: missing coordinates", station_id)
            return

        valid = station.get("status", "").lower() == "online"
        try:
            age = float(station["age"])
            valid = valid and math.isfinite(age) and 0 <= age <= self.max_age
        except (KeyError, ValueError, TypeError):
            valid = False

        values = None
        timestamp = None
        if valid:
            try:
                raw = station["data"]
                fields = ("ws", "wg", "wdn", "ta", "pa", "rh")
                values = {field: float(raw[field]) for field in fields}
                valid = (all(math.isfinite(x) for x in values.values())
                         and values["ws"] >= 0 and values["wg"] >= 0
                         and 0 <= values["wdn"] <= 360
                         and values["pa"] > 0 and 0 <= values["rh"] <= 100)
                timestamp = int(datetime.strptime(
                    station["ts"], "%Y-%m-%d %H:%M:%S"
                ).replace(tzinfo=ZoneInfo("Europe/Bucharest")).timestamp())
            except (KeyError, ValueError, TypeError):
                valid = False

        # Treat all-zero sensor payload as suspect; keep station RED until checked.
        if valid and all(values[k] == 0 for k in ("ws", "wg", "wdn", "ta", "rh")):
            valid = False
            self.log.warning("Station %s: suspect all-zero sensor payload", station_id)

        altitude = station.get("elevation")
        if altitude is not None:
            altitude = float(altitude)
        saved = self.save_station(
            provider_id=station_id,
            names=StationNames(short_name=name, name=name),
            latitude=float(lat), longitude=float(lon),
            status=StationStatus.GREEN if valid else StationStatus.RED,
            altitude=altitude,
            timezone=None,  # Let winds.mobi resolve the station location timezone.
            url={"default": self.provider_url},
        )
        if not valid or self.has_measure(saved, timestamp):
            return
        measure = self.create_measure(
            station=saved, _id=timestamp,
            wind_direction=values["wdn"] % 360,
            wind_average=Q_(values["ws"], ureg.meter / ureg.second),
            wind_maximum=Q_(values["wg"], ureg.meter / ureg.second),
            temperature=Q_(values["ta"], ureg.degC),
            humidity=values["rh"],
            pressure=Pressure(values["pa"], qnh=None, qff=None),
        )
        self.insert_measures(saved, [measure])


def paraweather():
    ParaWeather().process_data()


if __name__ == "__main__":
    paraweather()
