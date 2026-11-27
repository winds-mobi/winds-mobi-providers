"""SLF IMIS stations (WSL Institute for Snow and Avalanche Research SLF).

Data source: the SLF Measurement API, https://measurement-api.slf.ch (docs at /docs).
Licence: CC BY 4.0, see https://wsl.ch/en/services-produkte/slf-data-service

- `/public/api/imis/stations` lists the IMIS stations.
- `/public/api/imis/measurements` returns the last 24 hours of every station in one call, one row every 30 minutes.
- `/public/api/imis/station/{code}/measurements?period_in_days=7` returns up to 7 days of one station. It is only
  used to fill a gap, for example after the provider was down.

Station ids are `slf-{code}`, the same as with the former `public-meas-data.slf.ch` API, so the stations keep their
history. Wind speeds are in m/s.
"""

from collections import defaultdict

import arrow
import requests

from winds_mobi_provider import Q_, Provider, ProviderException, StationNames, StationStatus, ureg, user_agents

API_URL = "https://measurement-api.slf.ch/public/api/imis"

# Number of recent rows (one every 30 minutes) checked on each run
RECENT_MEASURES = 6


def wind_speed(value):
    return None if value is None else Q_(value, ureg.meter / ureg.second)


def has_wind(row: dict) -> bool:
    return any(row.get(key) is not None for key in ("DW_30MIN_MEAN", "VW_30MIN_MEAN", "VW_30MIN_MAX"))


def measure_key(row: dict) -> int:
    return arrow.get(row["measure_date"]).int_timestamp


def wind_rows_by_station(rows: list[dict]) -> dict[str, list[dict]]:
    """Rows with wind values, grouped by station code, newest first."""
    stations = defaultdict(list)
    for row in rows:
        if row.get("station_code") and row.get("measure_date") and has_wind(row):
            stations[row["station_code"]].append(row)
    for station_rows in stations.values():
        station_rows.sort(key=measure_key, reverse=True)
    return dict(stations)


def measure_values(row: dict) -> dict:
    """Arguments for `Provider.create_measure()` from one API row."""
    return {
        "wind_direction": row.get("DW_30MIN_MEAN"),
        "wind_average": wind_speed(row.get("VW_30MIN_MEAN")),
        "wind_maximum": wind_speed(row.get("VW_30MIN_MAX")),
        "temperature": row.get("TA_30MIN_MEAN"),
        "humidity": row.get("RH_30MIN_MEAN"),
    }


class Slf(Provider):
    provider_code = "slf"
    provider_name = "slf.ch"
    provider_url = "https://www.slf.ch"

    provider_urls = {
        "default": "https://whiterisk.ch/en/snow/station/IMIS/{id}",
        "en": "https://whiterisk.ch/en/snow/station/IMIS/{id}",
        "de": "https://whiterisk.ch/de/snow/station/IMIS/{id}",
        "fr": "https://whiterisk.ch/fr/snow/station/IMIS/{id}",
        "it": "https://whiterisk.ch/it/snow/station/IMIS/{id}",
    }

    def get_json(self, session, path, **params):
        result = session.get(f"{API_URL}{path}", params=params, timeout=(self.connect_timeout, self.read_timeout))
        result.raise_for_status()
        return result.json()

    def rows_to_save(self, session, station, rows: list[dict]) -> list[dict]:
        """The recent rows, or the last 7 days of the station when the oldest recent row is missing (a gap)."""
        recent = rows[:RECENT_MEASURES]
        if self.has_measure(station, measure_key(recent[-1])):
            return recent
        self.log.info(f"Filling the gap of station '{station['_id']}' with the last 7 days")
        week = self.get_json(session, f"/station/{station['pv-id']}/measurements", period_in_days=7)
        return wind_rows_by_station(week).get(station["pv-id"], recent)

    def process_data(self):
        try:
            self.log.info("Processing SLF data...")

            session = requests.Session()
            session.headers.update(user_agents.chrome)

            slf_stations = self.get_json(session, "/stations")
            rows_by_station = wind_rows_by_station(self.get_json(session, "/measurements"))

            for slf_station in slf_stations:
                station_id = None
                try:
                    slf_id = slf_station["code"]
                    station_id = self.get_station_id(slf_id)
                    rows = rows_by_station.get(slf_id)
                    if not rows:
                        # Snow stations without a wind sensor, or with no wind data in the last 24 hours
                        continue

                    station = self.save_station(
                        slf_id,
                        StationNames(short_name=slf_station["label"], name=slf_station["label"]),
                        slf_station["lat"],
                        slf_station["lon"],
                        StationStatus.GREEN,
                        altitude=slf_station["elevation"],
                        url={lang: url.format(id=slf_id) for lang, url in self.provider_urls.items()},
                    )
                    station_id = station["_id"]

                    measures = []
                    for row in self.rows_to_save(session, station, rows):
                        key = measure_key(row)
                        if self.has_measure(station, key):
                            continue
                        try:
                            measures.append(self.create_measure(station, key, **measure_values(row)))
                        except ProviderException as e:
                            self.log.warning(f"Error while processing measure '{key}' for station '{station_id}': {e}")
                        except Exception as e:
                            self.log.exception(
                                f"Error while processing measure '{key}' for station '{station_id}': {e}"
                            )

                    # Oldest first, so the station's last measure is the newest
                    self.insert_measures(station, sorted(measures, key=lambda measure: measure["_id"]))

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
