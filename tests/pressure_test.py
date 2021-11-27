import pytest

from winds_mobi_provider.uwxutils import TWxUtils


def test_altimeter_to_station():
    assert TWxUtils.AltimeterToStationPressure(1013, elevationM=1588) == pytest.approx(836.25, rel=1e-3)


def test_station_to_altimeter():
    assert TWxUtils.StationToAltimeter(836.25, elevationM=1588, algorithm="aaMADIS") == pytest.approx(1013, rel=1e-3)
