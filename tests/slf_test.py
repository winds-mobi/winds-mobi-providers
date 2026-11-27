from unittest import mock

import pytest

from providers import slf
from providers.slf import Slf, measure_values, wind_rows_by_station

# Cut from real responses of https://measurement-api.slf.ch on 2026-11-27
STATIONS = [
    {
        "code": "VSC1",
        "label": "Piz San Jon Dadaint",
        "lon": 10.3391321077,
        "lat": 46.7532597113,
        "elevation": 3092.0,
        "country_code": "CH",
        "canton_code": "GR",
        "type": "WIND",
    },
    {
        "code": "ADE2",
        "label": "Adelboden",
        "lon": 7.5612,
        "lat": 46.4823,
        "elevation": 1325.0,
        "country_code": "CH",
        "canton_code": "BE",
        "type": "SNOW_FLAT",
    },
]


def row(code, date, wind_average, wind_maximum, wind_direction, temperature=-12.09, humidity=18.46):
    return {
        "station_code": code,
        "measure_date": date,
        "HS": None,
        "TA_30MIN_MEAN": temperature,
        "RH_30MIN_MEAN": humidity,
        "VW_30MIN_MEAN": wind_average,
        "VW_30MIN_MAX": wind_maximum,
        "DW_30MIN_MEAN": wind_direction,
        "DW_30MIN_SD": 6.274,
    }


MEASURES = [
    row("VSC1", "2026-11-27T22:00:00Z", 1.732, 3.012, 40.52, -12.43, 23.38),
    row("VSC1", "2026-11-27T22:30:00Z", 2.893, 3.932, 61.21),
    # A snow station without wind values: never saved
    row("ADE2", "2026-11-27T22:30:00Z", None, None, None, -5.18, 51.08),
]


def test_wind_rows_by_station_drops_rows_without_wind_and_sorts_newest_first():
    rows = wind_rows_by_station(MEASURES)
    assert list(rows) == ["VSC1"]
    assert [r["measure_date"] for r in rows["VSC1"]] == ["2026-11-27T22:30:00Z", "2026-11-27T22:00:00Z"]


def test_measure_values_are_in_m_per_s():
    values = measure_values(MEASURES[1])
    assert values["wind_average"].to("km/h").magnitude == pytest.approx(10.4148)
    assert values["wind_maximum"].to("km/h").magnitude == pytest.approx(14.1552)
    assert values["wind_direction"] == 61.21
    assert values["temperature"] == -12.09
    assert values["humidity"] == 18.46


def test_measure_values_keep_missing_values_empty():
    values = measure_values(row("VSC1", "2026-11-27T22:30:00Z", None, 3.932, None, None, None))
    assert values["wind_average"] is None
    assert values["wind_direction"] is None
    assert values["temperature"] is None


@pytest.fixture
def provider():
    with mock.patch("winds_mobi_provider.provider.MongoClient"), mock.patch("winds_mobi_provider.provider.redis"):
        provider = Slf()
    provider.mongo_db.stations_fix.find_one.return_value = None
    provider.save_station = mock.Mock(
        side_effect=lambda slf_id, *args, **kwargs: {"_id": f"slf-{slf_id}", "pv-id": slf_id, "alt": 3092, "tz": "UTC"}
    )
    provider.insert_measures = mock.Mock()
    return provider


def fake_api(urls):
    def get(url, params=None, timeout=None):
        urls.append((url, params))
        response = mock.Mock()
        path = url.removeprefix(slf.API_URL)
        if path == "/stations":
            response.json.return_value = STATIONS
        elif path == "/measurements":
            response.json.return_value = MEASURES
        elif path == "/station/VSC1/measurements":
            response.json.return_value = [row("VSC1", "2026-11-21T12:00:00Z", 5.0, 8.0, 270.0)] + MEASURES[:2]
        else:
            raise AssertionError(f"Unexpected url {url}")
        return response

    return get


def run(provider, stored):
    urls = []
    provider.has_measure = mock.Mock(side_effect=lambda station, key: key in stored)
    with mock.patch("providers.slf.requests.Session") as session:
        session.return_value.get.side_effect = fake_api(urls)
        provider.process_data()
    return urls


def test_saves_wind_stations_with_their_old_ids(provider):
    run(provider, stored={1795818600 - 1800})  # 22:00 already stored

    provider.save_station.assert_called_once()
    args, kwargs = provider.save_station.call_args
    assert args[0] == "VSC1"
    assert args[1].short_name == "Piz San Jon Dadaint"
    assert (args[2], args[3]) == (46.7532597113, 10.3391321077)
    assert kwargs["altitude"] == 3092.0
    assert kwargs["url"]["default"] == "https://whiterisk.ch/en/snow/station/IMIS/VSC1"
    assert kwargs["url"]["de"] == "https://whiterisk.ch/de/snow/station/IMIS/VSC1"

    station, measures = provider.insert_measures.call_args.args
    assert station["_id"] == "slf-VSC1"
    assert len(measures) == 1
    measure = measures[0]
    assert measure["_id"] == 1795818600  # 2026-11-27T22:30:00Z
    assert measure["w-avg"] == 10.4
    assert measure["w-max"] == 14.2
    assert measure["w-dir"] == 61
    assert measure["temp"] == -12.1
    assert measure["hum"] == 18.5


def test_recent_rows_only_when_there_is_no_gap(provider):
    urls = run(provider, stored={1795818600 - 1800})
    assert [url.removeprefix(slf.API_URL) for url, params in urls] == ["/stations", "/measurements"]


def test_fills_a_gap_with_the_last_7_days(provider):
    urls = run(provider, stored=set())

    assert (f"{slf.API_URL}/station/VSC1/measurements", {"period_in_days": 7}) in urls
    station, measures = provider.insert_measures.call_args.args
    assert [m["_id"] for m in measures] == [1795262400, 1795816800, 1795818600]  # oldest first
    assert measures[0]["w-avg"] == 18.0
