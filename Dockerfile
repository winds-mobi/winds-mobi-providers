FROM python:3.10.11-slim-bullseye AS base

ENV LANG C.UTF-8
ENV LC_ALL C.UTF-8

RUN apt-get update; \
    apt-get --yes --no-install-recommends install pkg-config libpq5 libmariadb3

FROM base AS python-dependencies

RUN apt-get update; \
    apt-get --yes --no-install-recommends install build-essential libpq-dev libmariadb-dev curl
RUN curl -sSL https://install.python-poetry.org | python - --version 1.7.1

COPY pyproject.toml poetry.lock ./
RUN POETRY_VIRTUALENVS_IN_PROJECT=true /root/.local/bin/poetry install --only=main

FROM base AS runtime

COPY --from=python-dependencies /.venv /.venv
ENV PATH=/.venv/bin:$PATH

COPY . /opt/project/
WORKDIR /opt/project/
CMD ["./docker-cmd.sh"]
