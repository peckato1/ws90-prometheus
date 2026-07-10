"""PrometheusPublisher against an isolated CollectorRegistry."""

import prometheus_client as prom
import pytest

from rtl433_meteo.publish_prom import PrometheusPublisher


@pytest.fixture
def reg():
    return prom.CollectorRegistry()


@pytest.fixture
def publisher(reg):
    return PrometheusPublisher(clear_interval=0, prom_registry=reg)


def sample(reg, name, model, device_id, **extra):
    labels = {"model": model, "id": str(device_id)}
    labels.update(extra)
    return reg.get_sample_value(name, labels)


def test_ws90_callback_sets_metrics_and_info(reg, publisher, ws90):
    publisher.data_callback(ws90)

    assert sample(reg, "meteo_temperature_celsius", "Fineoffset-WS90", 15132) == 21.5
    assert sample(reg, "meteo_battery_ok", "Fineoffset-WS90", 15132) == 1.0
    assert sample(reg, "meteo_battery_volts", "Fineoffset-WS90", 15132) == pytest.approx(3.18)
    # firmware present, channel blanked (fixed info label union)
    assert sample(reg, "meteo_info", "Fineoffset-WS90", 15132, firmware="126", channel="") == 1.0


def test_vevor_callback_does_not_crash_on_missing_firmware(reg, publisher, vevor):
    # The original bug: publisher assumed every device sends `firmware`.
    publisher.data_callback(vevor)

    assert sample(reg, "meteo_temperature_celsius", "Vevor-7in1", 63735) == 20.9
    assert sample(reg, "meteo_battery_ok", "Vevor-7in1", 63735) == 1.0
    # channel 0 is falsy but present -> exported as "0", firmware blanked
    assert sample(reg, "meteo_info", "Vevor-7in1", 63735, firmware="", channel="0") == 1.0
    # WS90-only gauges have no Vevor series
    assert sample(reg, "meteo_supercap_volts", "Vevor-7in1", 63735) is None


def test_same_id_different_models_do_not_collide(reg, publisher, ws90, vevor):
    vevor["id"] = ws90["id"]
    publisher.data_callback(ws90)
    publisher.data_callback(vevor)

    assert sample(reg, "meteo_temperature_celsius", "Fineoffset-WS90", ws90["id"]) == 21.5
    assert sample(reg, "meteo_temperature_celsius", "Vevor-7in1", ws90["id"]) == 20.9


def test_clear_metrics_removes_only_that_series(reg, publisher, ws90, vevor):
    publisher.data_callback(ws90)
    publisher.data_callback(vevor)

    publisher.clear_metrics((vevor["model"], vevor["id"]))

    assert sample(reg, "meteo_temperature_celsius", "Vevor-7in1", 63735) is None
    assert sample(reg, "meteo_temperature_celsius", "Fineoffset-WS90", 15132) == 21.5


def test_clear_interval_zero_registers_no_timer(publisher, ws90):
    publisher.data_callback(ws90)
    assert publisher.timers == {}
