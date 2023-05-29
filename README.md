winds.mobi - real-time weather observations
===========================================

[![Follow us on https://www.facebook.com/WindsMobi/](https://img.shields.io/badge/facebook-follow_us-blue)](https://www.facebook.com/WindsMobi/)

[winds.mobi](http://winds.mobi): Paraglider pilot, kitesurfer, check real-time weather conditions of your favorite spots
on your smartphone, your tablet or your computer.

winds-mobi-providers
--------------------

Python scripts that get the weather data from different providers and save it in a common format into mongodb. 
This project use Google Cloud APIs to compute any missing station details (altitude, name, timezone, ...).
Google Cloud API results are cached with redis.

### Dependencies

- python 3.10 and [poetry](https://python-poetry.org) 
- mongodb 4.4
- redis
- Google Cloud API key

See [settings.py](https://github.com/winds-mobi/winds-mobi-providers/blob/main/settings.py)

### Run the project with docker compose (simple way)

Create a `.env` file from `.env.template` which will be read by docker compose:

- fill GOOGLE_API_KEY with you own [Google Cloud API key](https://cloud.google.com/docs/authentication/api-keys#creating_an_api_key)
- optionally fill the missing secrets for each provider

Then start the external services and the providers scheduler:

- `docker compose --profile=scheduler up --build`

Some providers need [winds-mobi-admin](https://github.com/winds-mobi/winds-mobi-admin#run-the-project-with-docker-compose-simple-way) running to get stations metadata.

### Run the project locally on macOS

#### Install dependencies

- `brew install openssl`
- `export LDFLAGS=-L/usr/local/opt/openssl/lib`

- `brew install libpq`
- `export PATH=/usr/local/opt/libpq/bin:$PATH`

- `brew install mysql-client`
- `export PATH=/usr/local/opt/mysql-client/bin:$PATH`

#### Python environment

- `poetry install`
- `poetry shell`

Create a `.env.localhost` file from `.env.localhost.template` which will be read by `dotenv` for our local commands:

- fill GOOGLE_API_KEY with you own [Google Cloud API key](https://cloud.google.com/docs/authentication/api-keys#creating_an_api_key)
- optionally fill the missing secrets for each provider

#### External services with docker compose

Create a `.env` file from `.env.template` which will be read by docker compose.

Then start the external services:

- `docker compose up`

#### Run the scheduler

- `dotenv -f .env.localhost run python run_providers.py`

#### Run only a provider

- `dotenv -f .env.localhost run python providers/ffvl.py`

### Contributing

#### Checking the code style

Format your code: `poetry run black .`

Run the linter: `poetry run flake8 .`

#### Add a new provider to winds.mobi

You know a good weather station that would be useful for many paraglider pilots or kitesurfers? 

Awesome! Fork this repository and create a pull request with your new provider code. It's easy, look at the following
example:

providers/my_provider.py
```
import arrow
import requests

from winds_mobi_provider import Provider, ProviderException, StationStatus, ureg, Q_, Pressure


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
                        short_name=station["name"],
                        name=None,  # Lets winds.mobi provide the full name with the help of Google Geocoding API
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

##### And test it

Start the external services:

- `docker compose up`

Build a Docker image containing your new provider `providers/my_provider.py`:

- `docker build --tag=winds.mobi/my_provider .`

Then run your provider inside a container with:

- `docker run -it --rm --env-file=.env --network=winds-mobi-providers --entrypoint=python winds.mobi/my_provider -m providers.my_provider`

To avoid building a new image on every change, you can mount your local source to the container directory `/opt/project` 
with a Docker volume:

- `docker run -it --rm --env-file=.env --network=winds-mobi-providers --volume=$(pwd):/opt/project --entrypoint=python winds.mobi/my_provider -m providers.my_provider`

Licensing
---------

Please see the file called [LICENSE.txt](https://github.com/winds-mobi/winds-mobi-providers/blob/main/LICENSE.txt)
