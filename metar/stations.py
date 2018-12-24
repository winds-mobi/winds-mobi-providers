import json

import requests


def dms2dd(degrees, minutes, direction):
    dd = float(degrees) + float(minutes)/60
    if direction == 'S' or direction == 'W':
        dd *= -1
    return dd


with open('stations.json', 'w') as out_file:
    # Another maintained version here: http://weather.rap.ucar.edu/surface/stations.txt
    request = requests.get('http://aviationweather.gov/docs/metar/stations.txt', stream=True)
    stations = {}
    for line in request.iter_lines():
        data = line.decode('ascii')
        if data:
            if data[0] == '!' or len(data) != 83:
                continue

            province = data[0:2]
            station = data[3:19].strip()
            icao = data[20:24].strip()
            lat = dms2dd(data[39:41], data[42:44], data[44:45])
            lon = dms2dd(data[47:50], data[51:53], data[53:54])
            altitude = int(data[55:59])
            country = data[81:83]

            if icao:
                stations[icao] = {
                    'name': station,
                    'lat': lat,
                    'lon': lon,
                    'altitude': altitude,
                    'country': country
                }
    json.dump(stations, out_file)
