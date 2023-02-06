import collections

import arrow
import requests

from winds_mobi_provider import Provider, ProviderException, StationStatus, user_agents

Measure = collections.namedtuple("Measure", ("key", "wind_direction", "wind_average", "wind_maximum", "temperature"))


class Slf(Provider):
    provider_code = "slf"
    provider_name = "slf.ch"
    provider_url = "https://www.slf.ch"

    provider_urls = {
        "default": "https://whiterisk.ch/en/snow/station/{network}/{id}",
        "en": "https://whiterisk.ch/en/snow/station/{network}/{id}",
        "de": "https://whiterisk.ch/de/snow/station/{network}/{id}",
        "fr": "https://whiterisk.ch/fr/snow/station/{network}/{id}",
        "it": "https://whiterisk.ch/it/snow/station/{network}/{id}",
    }

    def process_data(self):
        try:
            self.log.info("Processing SLF data...")

            session = requests.Session()
            session.headers.update(user_agents.chrome)

            result = session.get(
                "https://public-meas-data.slf.ch" "/public/station-data/timepoint/WIND_MEAN/current/geojson",
                timeout=(self.connect_timeout, self.read_timeout),
            )
            slf_stations = result.json()

            for slf_station in slf_stations["features"]:
                station_id = None
                try:
                    slf_id = slf_station["properties"]["code"]
                    slf_network = slf_station["properties"]["network"]
                    if slf_network == "SMN":
                        self.log.warning(
                            f"Ignore station '{slf_id}' part of the SMN network (SwissMetNet from MeteoSwiss)"
                        )
                    station_id = f"{self.provider_code}-{slf_id}"

                    station = self.save_station(
                        slf_id,
                        slf_station["properties"]["label"],
                        slf_station["properties"]["label"],
                        slf_station["geometry"]["coordinates"][1],
                        slf_station["geometry"]["coordinates"][0],
                        StationStatus.GREEN,
                        altitude=slf_station["properties"]["elevation"],
                        url={
                            lang: url.format(network=slf_network, id=slf_id) for lang, url in self.provider_urls.items()
                        },
                    )
                    station_id = station["_id"]

                    result = session.get(
                        f"https://public-meas-data.slf.ch"
                        f"/public/station-data/timeseries/current/{slf_network}/{slf_id}",
                        timeout=(self.connect_timeout, self.read_timeout),
                    )
                    slf_measure = result.json()

                    measures_collection = self.measures_collection(station_id)
                    new_measures = []
                    try:
                        timestamp = (
                            slf_station["properties"]["timestamp"] or slf_measure["windDirectionMean"]["timestamp"]
                        )
                    except KeyError:
                        timestamp = None
                    if not timestamp:
                        continue

                    key = arrow.get(timestamp).int_timestamp
                    if not self.has_measure(measures_collection, key):
                        try:
                            measure = self.create_measure(
                                station,
                                key,
                                slf_measure["windDirectionMean"]["value"],
                                slf_measure["windVelocityMean"]["value"],
                                slf_measure["windVelocityMax"]["value"],
                                temperature=slf_measure.get("temperatureAir", {}).get("value"),
                            )
                            new_measures.append(measure)
                        except KeyError as e:
                            self.log.warning(
                                f"Error while processing measure '{key}' for station '{station_id}': missing key {e}"
                            )
                        except ProviderException as e:
                            self.log.warning(f"Error while processing measure '{key}' for station '{station_id}': {e}")
                        except Exception as e:
                            self.log.exception(
                                f"Error while processing measure '{key}' for station '{station_id}': {e}"
                            )

                    self.insert_new_measures(measures_collection, station, new_measures)

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
