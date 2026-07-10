"""RtlReader.process_data dispatch/filtering."""

import pytest

from rtl433_meteo import stations
from rtl433_meteo.rtl_reader import RtlReader


class RecordingSignal:
    def __init__(self):
        self.sent = []

    def send(self, data):
        self.sent.append(data)


def make_reader(device_ids=()):
    sig = RecordingSignal()
    reader = RtlReader("true", stations.STATIONS.keys(), list(device_ids), sig, future=None)
    return reader, sig


def test_known_models_are_forwarded(ws90, vevor):
    reader, sig = make_reader()
    reader.process_data(ws90)
    reader.process_data(vevor)
    assert sig.sent == [ws90, vevor]


def test_unknown_model_is_ignored():
    reader, sig = make_reader()
    reader.process_data({"model": "Acurite-5n1", "id": 1})
    assert sig.sent == []


def test_message_without_id_is_ignored(ws90):
    reader, sig = make_reader()
    del ws90["id"]
    reader.process_data(ws90)
    assert sig.sent == []


def test_id_filter_restricts_devices(ws90, vevor):
    reader, sig = make_reader(device_ids=[ws90["id"]])
    reader.process_data(ws90)   # id matches
    reader.process_data(vevor)  # id filtered out
    assert sig.sent == [ws90]
