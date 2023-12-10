winds-mobi-providers
====================

Python scripts that get the weather data from different providers and save it in a common format into mongodb. 
This project use Google Cloud APIs to compute any missing station details (altitude, name, timezone, ...).
Google Cloud API results are cached with redis.

## Run the project with docker compose (simple way)
### Dependencies
- [Docker](https://docs.docker.com/get-docker/)
- Google Cloud API key
- Providers secrets (optional)

Create an `.env` file from `.env.template` read by docker compose:
- `cp .env.template .env`

In `.env`:
- fill GOOGLE_API_KEY with you own [Google Cloud API key](https://cloud.google.com/docs/authentication/api-keys#creating_an_api_key)
- optionally fill the missing secrets for each provider you want to test

### Start the databases
- `docker compose -f compose.services.yaml up`

### Run the providers
- `docker compose up`

Or, run only a specific provider:
- `PROVIDER=ffvl docker compose up`

Some providers need [winds-mobi-admin](https://github.com/winds-mobi/winds-mobi-admin#run-the-project-with-docker-compose-simple-way) running to get stations metadata.

## Run the project locally
### Dependencies
- [Homebrew](https://brew.sh)
- Python 3.10
- [Poetry 1.7.1](https://python-poetry.org)
- Google Cloud API key
- Providers secrets (optional)

Create an `.env.localhost` file from `.env.localhost.template` read by `dotenv` for our local commands:
- `cp .env.localhost.template .env.localhost`

In `env.localhost`:
- fill GOOGLE_API_KEY with you own [Google Cloud API key](https://cloud.google.com/docs/authentication/api-keys#creating_an_api_key)
- optionally fill the missing secrets for each provider you want to test

#### On macOS
Install libraries with homebrew:
- `brew install libpq`
- `brew install mysql-client`

### Create python virtual environment and install dependencies
#### On macOS
- `poetry install`

### Activate python virtual environment
- `poetry shell`

### Start the databases
You must already have the `.env` file created in the [previous section](#run-the-project-with-docker-compose-simple-way).
- `docker compose -f compose.services.yaml up`

### Run the providers
- `dotenv -f .env.localhost run python run_scheduler.py`

Or, run only a specific provider:
- `dotenv -f .env.localhost run python -m providers.ffvl`

Some providers need [winds-mobi-admin](https://github.com/winds-mobi/winds-mobi-admin#run-the-project-with-docker-compose-simple-way) running to get stations metadata.

### Checking the code style
Format python code:
- `black .`

Run the linter tools:
- `flake8 .`
- `isort .`

## Contributing
### Add a new provider to winds.mobi
You know good quality weather stations that would be useful for many paraglider pilots or kitesurfers? 

Awesome! Fork this repository and open a pull request with your new provider code. It's easy, look at the following
example:

providers/my_provider.py
```
import arrow
import requests

from winds_mobi_provider import Q_, Pressure, Provider, ProviderException, StationNames, StationStatus, ureg


class MyProvider(Provider):
    provider_code = "my-provider"
    provider_name = "my-provider.com"

    def process_data(self):
        self.log.info("Processing MyProvider data...")
        try:
            # data = requests.get(
            #     "https://api.my-provider.com/stations.json", timeout=(self.connect_timeout, self.read_timeout)
            # ).json()
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
                        # Lets winds.mobi provide the full name (if found) with the help of Google Geocoding API
                        names=lambda names: StationNames(
                            short_name=station["name"], name=names.name or station["name"]
                        ),
                        latitude=station["latitude"],
                        longitude=station["longitude"],
                        status=StationStatus.GREEN if station["status"] == "ok" else StationStatus.RED,
                        url=f"https://my-provider.com/stations/{station['id']}",
                    )

                    measure_key = arrow.get(station["measures"][0]["time"], "YYYY-MM-DD HH:mm:ssZZ").int_timestamp
                    measures_collection = self.measures_collection(winds_station["_id"])

                    if not self.has_measure(measures_collection, measure_key):
                        new_measure = self.create_measure(
                            for_station=winds_station,
                            _id=measure_key,
                            wind_direction=station["measures"][0]["windDirection"],
                            wind_average=Q_(station["measures"][0]["windAverage"], ureg.meter / ureg.second),
                            wind_maximum=Q_(station["measures"][0]["windMaximum"], ureg.meter / ureg.second),
                            temperature=Q_(station["measures"][0]["temperature"], ureg.degC),
                            pressure=Pressure(station["measures"][0]["pressure"], qnh=None, qff=None),
                        )
                        self.insert_new_measures(measures_collection, winds_station, [new_measure])

                except ProviderException as e:
                    self.log.warning(f"Error while processing station '{station['id']}': {e}")
                except Exception as e:
                    self.log.exception(f"Error while processing station '{station['id']}': {e}")

        except Exception as e:
            self.log.exception(f"Error while processing MyProvider: {e}")

        self.log.info("...Done !")


def my_provider():
    MyProvider().process_data()


if __name__ == "__main__":
    my_provider()
```

## Licensing
winds.mobi is licensed under the AGPL License, Version 3.0. See [LICENSE.txt](LICENSE.txt)
