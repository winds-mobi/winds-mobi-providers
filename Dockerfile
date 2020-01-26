FROM python:3.7-slim-buster

RUN apt-get update; \
apt-get --yes --no-install-recommends install build-essential python-scipy libpq-dev libmariadb-dev-compat; \
rm -rf /var/lib/apt/lists/*

ADD . /app
WORKDIR /app

RUN pip install pipenv
RUN pipenv install --system --deploy

RUN apt-get --yes --purge autoremove build-essential

ENTRYPOINT ["python"]
