"""Configuration-driven registry of supported rtl_433 weather stations.

Adding a new station is a data-entry task: describe its ``rtl_433`` model string
and map its JSON fields onto the shared, generic metrics below. No changes to the
reader or publishers are required.

Metrics are shared across all stations and disambiguated by the ``model`` and ``id``
labels, so different stations may report the same physical quantity (e.g. wind speed)
under one metric name even when their raw units differ -- the per-field ``transform``
normalizes them (wind is always exported in m/s, rain in metres, ...).
"""

import dataclasses
from collections.abc import Callable


@dataclasses.dataclass(frozen=True)
class Metric:
    """A single generic gauge, registered once and shared by every station."""

    name: str
    description: str


@dataclasses.dataclass(frozen=True)
class Field:
    """Maps one rtl_433 JSON key of a station onto a shared metric.

    ``transform`` optionally converts the raw value into the metric's canonical
    unit (e.g. km/h -> m/s).
    """

    json_key: str
    metric_key: str
    transform: Callable[[float], float] | None = None

    def value(self, data: dict) -> float:
        raw = data[self.json_key]
        return raw if self.transform is None else self.transform(raw)


@dataclasses.dataclass(frozen=True)
class Station:
    """One supported rtl_433 model and how to read it.

    ``info_keys`` are the JSON keys this station contributes to the shared
    ``meteo_info`` metric (e.g. firmware for the WS90, channel for the Vevor).
    """

    model: str
    fields: tuple[Field, ...]
    info_keys: tuple[str, ...]


# Canonical metrics, keyed by a short name referenced from each station's fields.
# All are exported with the label set (model, id).
METRICS: dict[str, Metric] = {
    "temperature_celsius": Metric("meteo_temperature_celsius", "Temperature in Celsius"),
    "humidity_ratio": Metric("meteo_humidity_ratio", "Humidity in percent"),
    "battery_ok": Metric("meteo_battery_ok", "Battery status (1 = OK / full charge, 0 = depleted)"),
    "battery_volts": Metric("meteo_battery_volts", "Battery voltage"),
    "supercap_volts": Metric("meteo_supercap_volts", "Supercap voltage"),
    "wind_dir_degrees": Metric("meteo_wind_dir_degrees", "Wind direction in degrees"),
    "wind_avg_speed": Metric("meteo_wind_avg_speed", "Wind speed in m/s"),
    "wind_gust_speed": Metric("meteo_wind_gust_speed", "Wind gust speed in m/s"),
    "uvi": Metric("meteo_uvi", "UV index"),
    "light_lux": Metric("meteo_light_lux", "Light in lux"),
    "rain_m": Metric("meteo_rain_m", "Total rain in metres"),
    "rain_start": Metric("meteo_rain_start", "Rain start info"),
}

# Info metric carrying per-model textual details. The label set is the fixed union
# of every station's ``info_keys`` (missing keys are exported as ""), because
# prometheus_client requires a consistent set of info labels across all series.
INFO_METRIC_NAME = "meteo"
INFO_METRIC_DESC = "Weather station model information"
INFO_KEYS: tuple[str, ...] = ("firmware", "channel")


LABELS = ("model", "id")


STATIONS: dict[str, Station] = {
    station.model: station
    for station in (
        Station(
            model="Fineoffset-WS90",
            fields=(
                Field("temperature_C", "temperature_celsius"),
                Field("humidity", "humidity_ratio"),
                Field("battery_ok", "battery_ok"),
                Field("battery_mV", "battery_volts", lambda x: x / 1000),  # mV -> V
                Field("supercap_V", "supercap_volts"),
                Field("wind_dir_deg", "wind_dir_degrees"),
                Field("wind_avg_m_s", "wind_avg_speed"),
                Field("wind_max_m_s", "wind_gust_speed"),
                Field("uvi", "uvi"),
                Field("light_lux", "light_lux"),
                Field("rain_mm", "rain_m", lambda x: x / 1000),  # mm -> m
                Field("rain_start", "rain_start"),
            ),
            info_keys=("firmware",),
        ),
        Station(
            model="Vevor-7in1",
            fields=(
                Field("temperature_C", "temperature_celsius"),
                Field("humidity", "humidity_ratio"),
                Field("battery_ok", "battery_ok"),
                Field("wind_dir_deg", "wind_dir_degrees"),
                Field("wind_avg_km_h", "wind_avg_speed", lambda x: x / 3.6),  # km/h -> m/s
                Field("wind_max_km_h", "wind_gust_speed", lambda x: x / 3.6),  # km/h -> m/s
                Field("uvi", "uvi"),
                Field("light_lux", "light_lux"),
                Field("rain_mm", "rain_m", lambda x: x / 1000),  # mm -> m
            ),
            info_keys=("channel",),
        ),
    )
}
