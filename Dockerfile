FROM python:3.9-slim-buster AS base

ENV LANG C.UTF-8
ENV LC_ALL C.UTF-8

RUN apt-get update; \
apt-get --yes --no-install-recommends install python-scipy libpq5 libmariadb3

FROM base AS python-deps

RUN apt-get update; \
apt-get --yes --no-install-recommends install build-essential python-scipy libpq-dev libmariadb-dev

RUN pip install pipenv

COPY . .
RUN PIPENV_VENV_IN_PROJECT=1 pipenv install --deploy

FROM base AS runtime

ENV PATH="/.venv/bin:$PATH"

WORKDIR /app
COPY . .

FROM runtime AS production

COPY --from=python-deps /.venv /.venv
ENTRYPOINT ["python", "run_providers.py"]
