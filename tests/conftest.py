"""Shared fixtures for the rtl433-meteo test suite.

The sample records are real rtl_433 JSON messages captured from the two supported
stations (note ``channel: 0`` and integer ``battery_ok``/``firmware`` -- values that
naive code mishandles).
"""

import pytest

SAMPLE_VEVOR = {
    "time": "2026-07-10 21:06:09",
    "model": "Vevor-7in1",
    "id": 63735,
    "channel": 0,
    "battery_ok": 1,
    "temperature_C": 20.900,
    "humidity": 52,
    "wind_avg_km_h": 0.000,
    "wind_max_km_h": 0.000,
    "wind_dir_deg": 357,
    "rain_mm": 40.076,
    "uvi": 0.000,
    "light_lux": 500,
    "mic": "CHECKSUM",
}

SAMPLE_WS90 = {
    "time": "2026-07-10 21:06:32",
    "model": "Fineoffset-WS90",
    "id": 15132,
    "battery_ok": 1.000,
    "battery_mV": 3180,
    "temperature_C": 21.500,
    "humidity": 51,
    "wind_dir_deg": 79,
    "wind_avg_m_s": 1.000,
    "wind_max_m_s": 1.100,
    "uvi": 0.000,
    "light_lux": 600.000,
    "flags": 138,
    "rain_mm": 832.500,
    "rain_start": 0,
    "supercap_V": 5.200,
    "firmware": 126,
    "data": "3fff8ccddc------bac2ffaffa0000",
    "mic": "CRC",
}


@pytest.fixture
def vevor():
    return dict(SAMPLE_VEVOR)


@pytest.fixture
def ws90():
    return dict(SAMPLE_WS90)
