FROM python:3.13.10-slim-trixie AS base

RUN apt-get update; \
    apt-get --yes --no-install-recommends install pkg-config libpq5 libmariadb3

FROM base AS python-dependencies
COPY --from=ghcr.io/astral-sh/uv:0.9.16 /uv /uvx /bin/

RUN apt-get update; \
    apt-get --yes --no-install-recommends install build-essential libpq-dev libmariadb-dev curl

COPY pyproject.toml uv.lock ./
RUN uv sync --locked

FROM base AS runtime

COPY --from=python-dependencies /.venv /.venv
ENV PATH=/.venv/bin:$PATH

COPY . /opt/project/
WORKDIR /opt/project/
CMD ["./docker-cmd.sh"]
