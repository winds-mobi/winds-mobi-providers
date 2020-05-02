winds.mobi - real-time weather observations
===========================================

[![DockerHub](https://img.shields.io/docker/cloud/automated/windsmobi/winds-mobi-providers)](https://cloud.docker.com/u/windsmobi/repository/docker/windsmobi/winds-mobi-providers)
[![Follow us on https://www.facebook.com/WindsMobi/](https://img.shields.io/badge/facebook-follow_us-blue)](https://www.facebook.com/WindsMobi/)

[winds.mobi](http://winds.mobi): Paraglider pilot, kitesurfer, check real-time weather conditions of your favorite spots
on your smartphone, your tablet or your computer.

winds-mobi-providers
--------------------

Python 3.6 cronjobs that get the weather data from different providers and save it in a common format into mongodb. 
This project use Google Cloud APIs to compute any missing station details (altitude, name, timezone, ...).
Google Cloud API results are cached with redis.

### Requirements

- python >= 3.6 
- mongodb >= 3.0
- redis
- Google Cloud API key

See [settings.py](https://github.com/winds-mobi/winds-mobi-providers/blob/master/settings.py)

#### macOS

- `brew install mysql-client`
- `export PATH=/usr/local/opt/mysql-client/bin:$PATH`

- `brew install libpq`
- `export PATH=/usr/local/opt/libpq/bin:$PATH`

### Python environment

- `pipenv install`
- `pipenv shell`

### Run a provider

- `python holfuy.py`

### Add a new provider to winds.mobi

You know a good weather station that would be useful for many paraglider pilots or kitesurfers? 

Awesome! Fork this repository and create a pull request with your new provider code. It's easy, look at the following
example:

my_provider.py
```
import arrow
import requests

from winds_mobi_provider import Provider, StationStatus, ureg, Q_, Pressure


class MyProvider(Provider):
    provider_code = 'my-provider'
    provider_name = 'my-provider.com'

    def process_data(self):
        self.log.info('Processing MyProvider data...')
        data = requests.get(
            'https://api.my-provider.com/stations.json', timeout=(self.connect_timeout, self.read_timeout)
        )
        for data_dict in data.json():
            station = self.save_station(
                provider_id=data_dict['id'],
                short_name=data_dict['name'],
                name=None,  # Let's winds.mobi provide the full name with the help of Google Geocoding API
                latitude=data_dict['latitude'],
                longitude=data_dict['longitude'],
                status=StationStatus.GREEN if data_dict['status'] == 'ok' else StationStatus.RED
            )

            measure_key = arrow.get(data_dict['lastMeasure']['time'], 'YYYY-MM-DD HH:mm:ssZZ').timestamp
            measures_collection = self.measures_collection(station['_id'])
            
            if not self.has_measure(measures_collection, measure_key):
                new_measure = self.create_measure(
                    for_station=station,
                    _id=measure_key,
                    wind_direction=data_dict['lastMeasure']['windDirection'],
                    wind_average=Q_(data_dict['lastMeasure']['windAverage'], ureg.meter / ureg.second),
                    wind_maximum=Q_(data_dict['lastMeasure']['windMaximum'], ureg.meter / ureg.second),
                    temperature=Q_(data_dict['lastMeasure']['temp'], ureg.degC),
                    pressure=Pressure(qnh=Q_(data_dict['lastMeasure']['pressure'], ureg.hPa)),
                )
                self.insert_new_measures(measures_collection, station, [new_measure])
        self.log.info('...Done !')
```

Licensing
---------

Please see the file called [LICENSE.txt](https://github.com/winds-mobi/winds-mobi-providers/blob/master/LICENSE.txt)
