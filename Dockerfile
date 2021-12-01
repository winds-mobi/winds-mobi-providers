FROM python:3.9.9-slim-bullseye AS base

ENV LANG C.UTF-8
ENV LC_ALL C.UTF-8

RUN apt update; \
    apt --yes --no-install-recommends install libpq5 libmariadb3

FROM base AS python

RUN apt update; \
    apt --yes --no-install-recommends install build-essential libpq-dev libmariadb-dev
RUN pip install pipenv

COPY . .
RUN PIPENV_VENV_IN_PROJECT=1 pipenv install --deploy

FROM base AS runtime

ENV PATH="/.venv/bin:$PATH"

COPY . .

FROM runtime AS production

COPY --from=python /.venv /.venv
ENTRYPOINT ["python", "run_providers.py"]
