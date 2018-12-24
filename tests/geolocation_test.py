from commons.provider import Provider

tests = ('VAUD Airport ICAO', 'EGVA Airport ICAO', 'LSGG Airport ICAO')

for test in tests:
    print(test)
    try:
        print('autocomplete=', Provider()._Provider__get_place_autocomplete(test))
    except Exception as e:
        print(e)
    try:
        print('geocoding=', Provider()._Provider__get_place_geocoding(test))
    except Exception as e:
        print(e)
