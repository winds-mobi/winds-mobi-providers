import pytest

from providers.anm_romania import AnmRomania


def test_web_mercator_to_wgs84_brasov_ghimbav():
    lat, lon = AnmRomania.web_mercator_to_wgs84(
        2841559.570000,
        5731741.680000,
    )

    assert lat == pytest.approx(45.69585, abs=0.00001)
    assert lon == pytest.approx(25.52616, abs=0.00001)


@pytest.mark.parametrize(
    "value,expected_speed,expected_direction",
    [
        ("1.8 m/s, directia : NNV", 1.8, 337.5),
        ("4.9 m/s, directia : VNV", 4.9, 292.5),
        ("3.0 m/s, directia : V", 3.0, 270.0),
        ("4.0 m/s, directia : SSV", 4.0, 202.5),
    ],
)
def test_parse_wind(value, expected_speed, expected_direction):
    speed, direction = AnmRomania.parse_wind(value)

    assert speed == expected_speed
    assert direction == expected_direction


def test_parse_wind_unavailable():
    assert AnmRomania.parse_wind("indisponibil") == (None, None)


def test_parse_pressure():
    assert AnmRomania.parse_pressure("958.2 mb, in crestere") == 958.2
    assert AnmRomania.parse_pressure("indisponibil") is None


def test_parse_temperature():
    assert AnmRomania.parse_temperature("12.0") == 12.0
    assert AnmRomania.parse_temperature("-1.5") == -1.5
    assert AnmRomania.parse_temperature("indisponibil") is None
