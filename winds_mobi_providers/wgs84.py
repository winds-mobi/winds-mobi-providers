import re

p = re.compile('[^\\d\\w]+')


def parse_dms(input):
    parts = p.split(input)
    return convert_dms_to_dd(parts[0], parts[1], parts[2], parts[3])


def convert_dms_to_dd(days, minutes, seconds, direction):
    dd = float(days) + float(minutes) / 60 + float(seconds) / (60 * 60)

    if (direction.lower() == 's') or (direction.lower() == 'w'):
        dd *= -1

    return dd
