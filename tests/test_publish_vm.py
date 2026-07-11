"""VictoriaMetrics CSV construction (no network)."""

import datetime

import pytest
import requests

from rtl433_meteo import stations
from rtl433_meteo.publish_vm import VictoriaMetricsPublisher


@pytest.fixture
def publisher():
    return VictoriaMetricsPublisher("http://vm.example")


def _dt(data):
    return datetime.datetime.strptime(data["time"], "%Y-%m-%d %H:%M:%S")


def test_metrics_csv_uses_generic_names_and_transforms(publisher, ws90):
    station = stations.STATIONS[ws90["model"]]
    line, columns = publisher._construct_metrics(ws90, station, _dt(ws90))

    assert columns[0] == "1:time:unix_s"
    row = dict(zip((c.split(":")[-1] for c in columns[1:]), line[1:]))
    assert row["meteo_temperature_celsius"] == 21.5
    assert row["meteo_battery_volts"] == pytest.approx(3.18)
    assert row["meteo_rain_m"] == pytest.approx(0.8325)


def test_metrics_csv_skips_fields_absent_from_message(publisher, vevor):
    # rtl_433 does not always transmit every field; a real Vevor message arrived
    # without "uvi", which must be skipped rather than raise KeyError.
    del vevor["uvi"]
    station = stations.STATIONS[vevor["model"]]
    line, columns = publisher._construct_metrics(vevor, station, _dt(vevor))

    names = [c.split(":")[-1] for c in columns]
    assert "meteo_uvi" not in names
    assert "meteo_temperature_celsius" in names  # other fields still present
    # CSV column indices stay contiguous and aligned with the values.
    assert [c.split(":")[0] for c in columns] == [str(i) for i in range(1, len(columns) + 1)]
    assert len(line) == len(columns)


def test_info_csv_skips_absent_info_key(publisher, vevor):
    del vevor["channel"]
    station = stations.STATIONS[vevor["model"]]
    line, columns = publisher._construct_info(vevor, station, _dt(vevor))

    assert columns == ["1:time:unix_s", "2:metric:meteo_info"]
    assert line == [int(_dt(vevor).timestamp()), 1]


def test_vevor_info_csv_uses_channel_not_firmware(publisher, vevor):
    station = stations.STATIONS[vevor["model"]]
    line, columns = publisher._construct_info(vevor, station, _dt(vevor))

    assert columns == ["1:time:unix_s", "2:metric:meteo_info", "3:label:channel"]
    assert line[1] == 1  # info metric value
    assert line[2] == 0  # channel value, present even though falsy


def test_ws90_info_csv_uses_firmware(publisher, ws90):
    station = stations.STATIONS[ws90["model"]]
    line, columns = publisher._construct_info(ws90, station, _dt(ws90))

    assert columns[-1] == "3:label:firmware"
    assert line[-1] == 126


def test_post_passes_a_timeout(publisher, ws90, monkeypatch):
    calls = []

    def fake_post(url, **kwargs):
        calls.append(kwargs)

        class Resp:
            status_code = 204

            def raise_for_status(self):
                pass

        return Resp()

    monkeypatch.setattr("rtl433_meteo.publish_vm.requests.post", fake_post)
    publisher.data_callback(ws90)

    assert calls, "expected a POST to VictoriaMetrics"
    assert all(c.get("timeout") is not None for c in calls)


def test_extra_label_is_one_param_per_label(publisher, ws90, monkeypatch):
    # extra_label must be a list so requests sends it as repeated query params;
    # a single comma-joined string makes VictoriaMetrics store the model inside the
    # id label value (id="15132,model=Fineoffset-WS90").
    calls = []

    def fake_post(url, **kwargs):
        calls.append(kwargs["params"]["extra_label"])

        class Resp:
            status_code = 204

            def raise_for_status(self):
                pass

        return Resp()

    monkeypatch.setattr("rtl433_meteo.publish_vm.requests.post", fake_post)
    publisher.data_callback(ws90)

    for extra_label in calls:
        assert isinstance(extra_label, list)
        assert "id=15132" in extra_label
        assert "model=Fineoffset-WS90" in extra_label
        assert not any("," in label for label in extra_label)


def test_vm_outage_is_swallowed(publisher, ws90, monkeypatch):
    def boom(*a, **k):
        raise requests.ConnectionError("VM is down")

    monkeypatch.setattr("rtl433_meteo.publish_vm.requests.post", boom)
    # Must not raise -- a dead VM cannot be allowed to kill the reader thread.
    publisher.data_callback(ws90)


def test_successful_push_logs_at_info(publisher, ws90, monkeypatch, caplog):
    class Resp:
        status_code = 204

        def raise_for_status(self):
            pass

    monkeypatch.setattr("rtl433_meteo.publish_vm.requests.post", lambda *a, **k: Resp())
    with caplog.at_level("INFO", logger="rtl433_meteo.publish_vm"):
        publisher.data_callback(ws90)

    assert any("Pushed Fineoffset-WS90 id=15132" in r.message for r in caplog.records)
