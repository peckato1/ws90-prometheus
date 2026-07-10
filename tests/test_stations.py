"""Field mapping and unit-normalization for each station."""

import pytest

from rtl433_meteo import stations


def _mapped(data):
    station = stations.STATIONS[data["model"]]
    return {f.metric_key: f.value(data) for f in station.fields}


def test_every_field_maps_to_a_known_metric():
    for station in stations.STATIONS.values():
        for field in station.fields:
            assert field.metric_key in stations.METRICS


def test_every_station_info_key_is_in_the_shared_union():
    for station in stations.STATIONS.values():
        for key in station.info_keys:
            assert key in stations.INFO_KEYS


def test_ws90_units(ws90):
    m = _mapped(ws90)
    assert m["temperature_celsius"] == 21.5
    assert m["battery_volts"] == pytest.approx(3.18)  # mV -> V
    assert m["rain_m"] == pytest.approx(0.8325)  # mm -> m
    assert m["wind_avg_speed"] == 1.0  # already m/s, unchanged
    assert m["wind_gust_speed"] == 1.1


def test_vevor_wind_is_normalized_to_m_s(vevor):
    vevor["wind_avg_km_h"] = 36.0
    vevor["wind_max_km_h"] = 72.0
    m = _mapped(vevor)
    assert m["wind_avg_speed"] == pytest.approx(10.0)  # 36 km/h -> 10 m/s
    assert m["wind_gust_speed"] == pytest.approx(20.0)
    assert m["rain_m"] == pytest.approx(0.040076)  # mm -> m


def test_vevor_has_no_ws90_only_fields(vevor):
    m = _mapped(vevor)
    assert "supercap_volts" not in m
    assert "battery_volts" not in m
    assert "rain_start" not in m
