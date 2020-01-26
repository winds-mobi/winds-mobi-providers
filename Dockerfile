FROM python:3.7-slim-buster

# PHP 7.3 is required by JDC provider
RUN apt-get update; \
DEBIAN_FRONTEND=noninteractive apt-get --yes --no-install-recommends install build-essential \
python-scipy libpq-dev libmariadb-dev-compat php7.3-cli; \
rm -rf /var/lib/apt/lists/*

ADD . /app
WORKDIR /app

RUN pip install pipenv
RUN pipenv install --system --deploy

RUN apt-get --yes --purge autoremove build-essential

ENTRYPOINT ["python"]
