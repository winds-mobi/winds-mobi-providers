import arrow

import settings
import requests
from winds_mobi_provider import Q_, Pressure, Provider, ProviderException, StationNames, StationStatus, ureg


class KachelmannWetterStation:
    def __init__(self, station_id, name):
        self.id = station_id
        self.name = name


class KachelmannWetterProvider(Provider):
    provider_code = "kachelmannwetter"
    provider_name = "kachelmannwetter.com"
    provider_url = "https://api.kachelmannwetter.com"

    def process_data(self):
        headers = {"x-api-Key": settings.KACHELMANN_API_KEY}

        self.log.info("Processing wunderground data...")
        try:
            # TODO move station list to admin_db?
            # KM0023 = wetter station from Gleitschirm Club Montafon www.gscm.at
            stations = {KachelmannWetterStation(station_id="KM0023", name="schruns0at")}

            for station in stations:
                url = "https://api.kachelmannwetter.com/v02/station/" + station.id + "/observations/latest"

                response = requests.get(url, timeout=(self.connect_timeout, self.read_timeout), headers=headers)
                self.log.info(response)
                data = response.json()

                try:
                    winds_station = self.save_station(
                        provider_id=data["stationId"],
                        # Let winds.mobi provide the full name (if found) with the help of Google Geocoding API
                        names=lambda names: StationNames(
                            short_name=data["name"],
                            name=names.name or data["name"],
                        ),
                        latitude=data["lat"],
                        longitude=data["lon"],
                        status=StationStatus.GREEN,
                        # If url is a dict, the keys must correspond to an ISO 639-1 language code. It also needs a
                        # "default" key, "english" if available. Here an example:
                        url={
                            "default": "https://kachelmannwetter.com/widget/station/" + station.name,
                        },
                    )
                    station_id = winds_station["_id"]

                    measures_collection = self.measures_collection(station_id)

                    # remove the seconds -> only store one measure per minute at max.
                    measure_key = arrow.get(data["data"]["temp"]["dateTime"]).int_timestamp

                    self.log.info(measure_key)

                    if not self.has_measure(measures_collection, measure_key):
                        try:
                            new_measure = self.create_measure(
                                for_station=winds_station,
                                _id=measure_key,
                                wind_direction=data["data"]["windDirection"]["value"],
                                wind_average=Q_(data["data"]["windSpeed"]["value"], ureg.meter / ureg.second),
                                wind_maximum=Q_(data["data"]["windGust10m"]["value"], ureg.meter / ureg.second),
                                temperature=Q_(data["data"]["temp"]["value"], ureg.degC),
                                pressure=Pressure(data["data"]["pressure"]["value"], qnh=None, qff=None),
                            )
                            self.insert_new_measures(measures_collection, winds_station, [new_measure])
                        except ProviderException as e:
                            self.log.warning(
                                f"Error while processing measure '{measure_key}' for station '{station_id}': {e}"
                            )
                        except Exception as e:
                            self.log.exception(
                                f"Error while processing measure '{measure_key}' for station '{station_id}': {e}"
                            )

                except ProviderException as e:
                    self.log.warning(f"Error while processing station '{station.id}': {e}")
                except Exception as e:
                    self.log.exception(f"Error while processing station '{station.id}': {e}")

        except Exception as e:
            self.log.exception(f"Error while processing KachelmannWetterProvider: {e}")

        self.log.info("...Done !")


def kachelmannwetter():
    KachelmannWetterProvider().process_data()


if __name__ == "__main__":
    kachelmannwetter()
