winds-mobi-providers
====================

Python scripts that get the weather data from different providers and save it in a common format into mongodb. 
This project use Google Cloud APIs to compute any missing station details (altitude, name, timezone, ...).
Google Cloud API results are cached with redis.

## Run the project with docker compose (simple way)
### Dependencies
- [Docker](https://docs.docker.com/get-docker/)
- [Google Cloud API](https://console.cloud.google.com) key
- Providers secrets (optional)

Create an `.env` file from `.env.template` read by docker compose:
- `cp .env.template .env`

In `.env`:
- fill GOOGLE_API_KEY with you own [Google Cloud API key](https://cloud.google.com/docs/authentication/api-keys#creating_an_api_key)
- optionally fill the missing secrets for each provider you want to test

### Build and run the project
- `docker compose --profile=application up`

Or, run only a specific provider:
- `PROVIDER=myexample docker compose --profile=application up`

Some providers need [winds-mobi-admin](https://github.com/winds-mobi/winds-mobi-admin#run-the-project-with-docker-compose-simple-way) running to get stations metadata.

## Run the project locally
### Dependencies
- [Homebrew](https://brew.sh)
- [uv](https://docs.astral.sh/uv/)
- [dotenvx](https://dotenvx.com/docs/)
- [Google Cloud API](https://console.cloud.google.com) key
- Providers secrets (optional)

Create an `.env.localhost` file from `.env.localhost.template` read by `dotenv` for our local commands:
- `cp .env.localhost.template .env.localhost`

In `env.localhost`:
- fill GOOGLE_API_KEY with you own [Google Cloud API key](https://cloud.google.com/docs/authentication/api-keys#creating_an_api_key)
- optionally fill the missing secrets for each provider you want to test

#### On macOS
Install libraries with homebrew:
- `brew install postgresql`
- `brew install mysql-client`
- `export PKG_CONFIG_PATH="/usr/local/opt/mysql-client/lib/pkgconfig"`

### Create python virtual environment and install dependencies
- `uv python install`
- `uv sync`

### Start the databases
You must already have the `.env` file created in the [previous section](#run-the-project-with-docker-compose-simple-way).
- `docker compose up`

### Run the providers
- `dotenvx run -f .env.localhost -- uv run python run_scheduler.py`

Or, run only a specific provider:
- `dotenvx run -f .env.localhost -- uv run python -m providers.ffvl`

Some providers need [winds-mobi-admin](https://github.com/winds-mobi/winds-mobi-admin#run-the-project-with-docker-compose-simple-way) running to get stations metadata.

### Checking the code style
Run the linter:
- `uv run ruff check`

Run the formatter:
- `uv run ruff format`

### Run the tests
- `uv run pytest`

## Contributing
### Add a new provider to winds.mobi
You know good quality weather stations that would be useful for many paraglider pilots or kitesurfers? 

Awesome! Fork this repository and open a pull request with your new provider code. It's easy, look at the following
example: [providers/myexample.py](providers/myexample.py)

## Licensing
winds.mobi is licensed under the AGPL License, Version 3.0. See [LICENSE.txt](LICENSE.txt)
