import arrow
import arrow.parser
import requests

from winds_mobi_provider import Q_, Pressure, Provider, ProviderException, StationNames, StationStatus, ureg


class Holfuy(Provider):
    provider_code = "holfuy"
    provider_name = "holfuy.com"
    provider_url = "https://holfuy.com"

    def process_data(self):
        try:
            self.log.info("Processing Holfuy data...")
            holfuy_stations = requests.get(
                "https://api.holfuy.com/stations/stations.json", timeout=(self.connect_timeout, self.read_timeout)
            ).json()
            holfuy_data = requests.get(
                "https://api.holfuy.com/live/?s=all&m=JSON&tu=C&su=km/h&utc",
                timeout=(self.connect_timeout, self.read_timeout),
            ).json()
            holfuy_measures = {}
            for holfuy_measure in holfuy_data["measurements"]:
                holfuy_measures[holfuy_measure["stationId"]] = holfuy_measure

            for holfuy_station in holfuy_stations["holfuyStationsList"]:
                holfuy_id = None
                station_id = None
                try:
                    holfuy_id = holfuy_station["id"]
                    name = holfuy_station["name"]
                    location = holfuy_station["location"]
                    latitude = location.get("latitude")
                    longitude = location.get("longitude")
                    if (latitude is None or longitude is None) or (latitude == 0 and longitude == 0):
                        raise ProviderException("No geolocation found")
                    altitude = location.get("altitude")

                    station = self.save_station(
                        holfuy_id,
                        StationNames(short_name=name, name=name),
                        latitude,
                        longitude,
                        StationStatus.GREEN,
                        altitude=altitude,
                        url={
                            "default": f"{self.provider_url}/en/weather/{holfuy_id}",
                            "en": f"{self.provider_url}/en/weather/{holfuy_id}",
                            "de": f"{self.provider_url}/de/weather/{holfuy_id}",
                            "fr": f"{self.provider_url}/fr/weather/{holfuy_id}",
                            "it": f"{self.provider_url}/it/weather/{holfuy_id}",
                        },
                    )
                    station_id = station["_id"]

                    if holfuy_id not in holfuy_measures:
                        raise ProviderException(
                            f"Station '{name}' not found in 'api.holfuy.com/live/': type='{holfuy_station['type']}'"
                        )
                    holfuy_measure = holfuy_measures[holfuy_id]
                    last_measure_date = arrow.get(holfuy_measure["dateTime"])
                    key = last_measure_date.int_timestamp
                    if not self.has_measure(station, key):
                        measure = self.create_measure(
                            station,
                            key,
                            holfuy_measure["wind"]["direction"],
                            Q_(holfuy_measure["wind"]["speed"], ureg.kilometer / ureg.hour),
                            Q_(holfuy_measure["wind"]["gust"], ureg.kilometer / ureg.hour),
                            temperature=(
                                Q_(holfuy_measure["temperature"], ureg.degC)
                                if "temperature" in holfuy_measure
                                else None
                            ),
                            pressure=Pressure(
                                qfe=None,
                                qnh=Q_(holfuy_measure["pressure"], ureg.hPa) if "pressure" in holfuy_measure else None,
                                qff=None,
                            ),
                        )
                        self.insert_measures(station, measure)

                except ProviderException as e:
                    self.log.warning(f"Error while processing station '{station_id or holfuy_id}': {e}")
                except Exception as e:
                    self.log.exception(f"Error while processing station '{station_id or holfuy_id}': {e}")

        except Exception as e:
            self.log.exception(f"Error while processing Holfuy: {e}")

        self.log.info("Done !")


def holfuy():
    Holfuy().process_data()


if __name__ == "__main__":
    holfuy()
