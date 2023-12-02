from unittest import mock

import pytest
import requests

from winds_mobi_provider import Provider


@pytest.mark.skip("Need a redis connection to Google API caches")
@pytest.mark.parametrize(
    "station_id,expected_name",
    [("metar-LSMP", "Payerne"), ("metar-LSGC", "Aero Group S.A."), ("metar-LSGG", "Geneva Airport")],
)
@mock.patch("winds_mobi_provider.provider.MongoClient")
def test_parse_reverse_geocoding_results(mongodb, station_id, expected_name):
    lon, lat = requests.get(f"https://winds.mobi/api/2.3/stations/{station_id}").json()["loc"]["coordinates"]
    provider = Provider()
    short_name, name = provider._Provider__parse_reverse_geocoding_results(f"address2/{lat},{lon}", None, None, None)
    assert short_name == expected_name
    assert name == expected_name
