import math


def dm_to_dd(s):
    d, m = s.split('°')
    dd = float(d) + float(m.strip()[:-1]) / 60
    return dd


def ch_to_wgs_lat(y, x):
    """Convert CH y/x to WGS lat"""

    # Converts military to civil and  to unit = 1000km
    # Auxiliary values (% Bern)
    y_aux = (y - 600000)/1000000
    x_aux = (x - 200000)/1000000

    # Process lat
    lat = 16.9023892 \
        + 3.238272 * x_aux \
        - 0.270978 * math.pow(y_aux, 2) \
        - 0.002528 * math.pow(x_aux, 2) \
        - 0.0447 * math.pow(y_aux, 2) * x_aux \
        - 0.0140 * math.pow(x_aux, 3)

    # Unit 10000" to 1 " and converts seconds to degrees (dec)
    lat = lat * 100/36
    return lat


def ch_to_wgs_lon(y, x):
    """Convert CH y/x to WGS long"""

    # Converts military to civil and  to unit = 1000km
    # Auxiliary values (% Bern)
    y_aux = (y - 600000)/1000000
    x_aux = (x - 200000)/1000000

    # Process long
    lon = 2.6779094 \
        + 4.728982 * y_aux \
        + 0.791484 * y_aux * x_aux \
        + 0.1306 * y_aux * math.pow(x_aux, 2) \
        - 0.0436 * math.pow(y_aux, 3)

    # Unit 10000" to 1 " and converts seconds to degrees (dec)
    lon = lon * 100/36
    return lon
