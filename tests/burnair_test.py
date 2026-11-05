from unittest import mock

import pytest

from providers.burnair import Burnair
from winds_mobi_provider import StationNames, StationStatus

FEED = {
    "generated": "2026-11-05T10:23:09Z",
    "license": {"name": "CC BY 4.0"},
    "stations": [
        {
            "_id": "burnair-4",
            "pv-id": "4",
            "pv-code": "burnair",
            "pv-name": "burnair.ch",
            "short": "Grund",
            "name": "Grund",
            "alt": 627,
            "status": "green",
            "loc": {"type": "Point", "coordinates": [8.029703, 46.619611]},
            "last": {"_id": 1793872200, "w-dir": 226, "w-avg": 1, "w-max": 4},
            "historic": [
                {"_id": 1793872200, "w-dir": 226, "w-avg": 1, "w-max": 4},
                {"_id": 1793871600, "w-dir": 220, "w-avg": 2, "w-max": 5},
            ],
        },
        {
            "_id": "burnair-2",
            "pv-id": "2",
            "pv-code": "burnair",
            "pv-name": "burnair.ch",
            "short": "Montoz",
            "name": "Montoz",
            "status": "green",
            "loc": {"type": "Point", "coordinates": [7.21784, 47.2086]},
            "last": {"_id": 1793872200, "w-dir": 111, "w-avg": 11, "w-max": 19},
            "historic": [{"_id": 1793872200, "w-dir": 111, "w-avg": 11, "w-max": 19}],
        },
    ],
}


@pytest.fixture
def provider():
    with (
        mock.patch("winds_mobi_provider.provider.MongoClient"),
        mock.patch("winds_mobi_provider.provider.redis"),
        mock.patch("winds_mobi_provider.provider.TimezoneFinder"),
    ):
        provider = Burnair()
    provider.mongo_db.stations_fix.find_one.return_value = None
    provider.save_station = mock.Mock(side_effect=lambda provider_id, **kwargs: {"_id": f"burnair-{provider_id}"})
    provider.has_measure = mock.Mock(return_value=False)
    provider.insert_measures = mock.Mock()
    return provider


@pytest.fixture
def feed():
    with mock.patch("providers.burnair.requests.get") as get:
        get.return_value.json.return_value = FEED
        yield


def test_save_station(provider, feed):
    provider.process_data()

    grund = provider.save_station.call_args_list[0].kwargs
    assert grund["provider_id"] == "4"
    assert grund["latitude"] == 46.619611
    assert grund["longitude"] == 8.029703
    assert grund["status"] == StationStatus.GREEN
    assert grund["altitude"] == 627


def test_missing_altitude_is_left_to_winds_mobi(provider, feed):
    provider.process_data()

    assert provider.save_station.call_args_list[1].kwargs["altitude"] is None


def test_station_names(provider, feed):
    provider.process_data()

    # The lambda closes over the loop variable: the last station is the one to check here
    names = provider.save_station.call_args_list[1].kwargs["names"]
    assert names(StationNames("Tavannes", "Tavannes BE")) == StationNames("Montoz", "Tavannes BE")
    assert names(StationNames(None, None)) == StationNames("Montoz", "Montoz")


def test_measures_are_inserted_oldest_first_in_km_h(provider, feed):
    provider.process_data()

    station, measures = provider.insert_measures.call_args_list[0].args
    assert station["_id"] == "burnair-4"
    assert [measure["_id"] for measure in measures] == [1793871600, 1793872200]
    assert measures[1]["w-dir"] == 226
    assert measures[1]["w-avg"] == 1.0
    assert measures[1]["w-max"] == 4.0


def test_known_measures_are_skipped(provider, feed):
    provider.has_measure.side_effect = lambda station, key: key == 1793871600

    provider.process_data()

    _, measures = provider.insert_measures.call_args_list[0].args
    assert [measure["_id"] for measure in measures] == [1793872200]


def test_failing_station_does_not_stop_the_others(provider, feed):
    provider.save_station.side_effect = [Exception("Boom"), {"_id": "burnair-2"}]

    provider.process_data()

    assert provider.insert_measures.call_count == 1
    assert provider.insert_measures.call_args.args[0]["_id"] == "burnair-2"
