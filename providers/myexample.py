import arrow

from winds_mobi_provider import Q_, Pressure, Provider, ProviderException, StationNames, StationStatus, ureg


class MyExample(Provider):
    provider_code = "myexample"
    provider_name = "myexample.com"
    provider_url = "https://www.myexample.com"

    def process_data(self):
        self.log.info("Processing MyExample data...")
        try:
            # data = requests.get(
            #     "https://api.myexample.com/stations.json", timeout=(self.connect_timeout, self.read_timeout)
            # ).json()
            # Result example:
            data = [
                {
                    "id": "station-1",
                    "name": "Station 1",
                    "latitude": 46.713,
                    "longitude": 6.503,
                    "status": "ok",
                    "measures": [
                        {
                            "time": arrow.now().format("YYYY-MM-DD HH:mm:ssZZ"),
                            "windDirection": 180,
                            "windAverage": 10.5,
                            "windMaximum": 20.1,
                            "temperature": 25.7,
                            "pressure": 1013,
                        }
                    ],
                }
            ]
            for station in data:
                try:
                    winds_station = self.save_station(
                        provider_id=station["id"],
                        # Let winds.mobi provide the full name (if found) with the help of Google Geocoding API
                        names=lambda names: StationNames(
                            short_name=station["name"], name=names.name or station["name"]
                        ),
                        latitude=station["latitude"],
                        longitude=station["longitude"],
                        status=StationStatus.GREEN if station["status"] == "ok" else StationStatus.RED,
                        # If url is a dict, the keys must correspond to an ISO 639-1 language code. It also needs a
                        # "default" key, "english" if available. Here an example:
                        url={
                            "default": f"{self.provider_url}/en/stations/{station['id']}",
                            "en": f"{self.provider_url}/en/stations/{station['id']}",
                            "fr": f"{self.provider_url}/fr/stations/{station['id']}",
                            "de": f"{self.provider_url}/de/stations/{station['id']}",
                        },
                    )
                    station_id = winds_station["_id"]

                    measures_collection = self.measures_collection(station_id)
                    for measure in station["measures"]:
                        measure_key = arrow.get(measure["time"], "YYYY-MM-DD HH:mm:ssZZ").int_timestamp
                        if not self.has_measure(measures_collection, measure_key):
                            try:
                                new_measure = self.create_measure(
                                    for_station=winds_station,
                                    _id=measure_key,
                                    wind_direction=measure["windDirection"],
                                    wind_average=Q_(measure["windAverage"], ureg.meter / ureg.second),
                                    wind_maximum=Q_(measure["windMaximum"], ureg.meter / ureg.second),
                                    temperature=Q_(measure["temperature"], ureg.degC),
                                    pressure=Pressure(measure["pressure"], qnh=None, qff=None),
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
                    self.log.warning(f"Error while processing station '{station['id']}': {e}")
                except Exception as e:
                    self.log.exception(f"Error while processing station '{station['id']}': {e}")

        except Exception as e:
            self.log.exception(f"Error while processing MyExample: {e}")

        self.log.info("...Done !")


def myexample():
    MyExample().process_data()


if __name__ == "__main__":
    myexample()
