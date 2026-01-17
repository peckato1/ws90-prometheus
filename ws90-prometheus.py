#!/usr/bin/env python

"""
WS90 Prometheus exporter

Usage:
    ws90-prometheus.py
        [--id=<id>]...
        [--port=<port>]
        [--clear=<clear>]
        [--log=<systemd|stderr>]
        [--log-level=<level>]
        [--cmd=<cmd>]
    ws90-prometheus.py --help

Options:
    --id=<id>               Device ID. Can be decimal or hex (prefix with 0x). Can specify multiple times. If not specified, all devices are being monitored.
    --port=<port>           Port to listen on [default: 8000]
    --log-level=<level>     Log level (debug, info, warning, error) [default: info]
    --clear=<clear>         Remove metrics for device after <clear> seconds. 0 for never. Useful for purging outdated metrics when the receiver stops receiving new data for a device. [default: 120]
    --log=<systemd|stderr>  Log to systemd journal or stderr [default: stderr]
    --cmd=<cmd>             Command to run [default: rtl_433 -Y minmax -f 868.3M -F json]
    --help                  Show this screen
"""

import asyncio
import blinker
import concurrent.futures
import docopt
import logging
import json
import prometheus_client as prom
import sys
import threading


logger = logging.getLogger(__name__)


class ResettableTimer:
    def __init__(self, interval, function, args=None):
        self.interval = interval
        self.function = function
        self.args = args if args is not None else tuple()
        self.timer = None

    def _start_timer(self):
        self.timer = threading.Timer(self.interval, self.function, self.args)
        self.timer.start()

    def start(self):
        if self.timer is not None:
            self.timer.cancel()
            self.timer = None
        self._start_timer()


def init_logging(log_type, log_level):
    if log_type == "systemd":
        try:
            import systemd.journal

            logger.addHandler(systemd.journal.JournalHandler())
        except ImportError:
            raise ImportError("systemd logging requested, but systemd.journal module not found")
    elif log_type == "stderr":
        handler = logging.StreamHandler(sys.stderr)
        formatter = logging.Formatter(fmt="%(asctime)s - %(levelname)8s - %(message)s")
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    else:
        raise docopt.DocoptExit(f"Invalid log type: {log_type}")

    match log_level.lower():
        case "debug":
            logger.setLevel(logging.DEBUG)
        case "info":
            logger.setLevel(logging.INFO)
        case "warning":
            logger.setLevel(logging.WARNING)
        case "error":
            logger.setLevel(logging.ERROR)
        case _:
            raise docopt.DocoptExit(f"Invalid log level: {log_level}")


class PrometheusPublisher:
    def __init__(self, clear_interval, metrics_data, model_data):
        self.clear_interval = clear_interval
        self.timers = dict()

        self.metrics = dict()
        self.postprocess = dict()
        for json_key, name, desc, postprocess in metrics_data:
            self.metrics[json_key] = prom.Gauge(name, desc, ["id"])

            if postprocess is not None:
                self.postprocess[json_key] = postprocess

        self.model_info = dict()
        self.model_keys = dict()
        for name, desc, keys in model_data:
            self.model_info[name] = prom.Info(name, desc, ["id"])
            self.model_keys[name] = keys

        self.last_sync = None

    def _postprocess(self, data, key):
        if key in self.postprocess:
            return self.postprocess[key](data[key])
        return data[key]

    def data_callback(self, data):
        device_id = data["id"]
        for k, model_info in self.model_info.items():
            model_info.labels(device_id).info({k: data[k] for k in self.model_keys[k]})

        for k, v in self.metrics.items():
            v.labels(device_id).set(self._postprocess(data, k))

        self.set_timer(data["model"], device_id, data["firmware"])

    def set_timer(self, model, device_id, firmware):
        if self.clear_interval == 0:
            return

        if device_id not in self.timers:
            self.timers[device_id] = ResettableTimer(
                self.clear_interval,
                self.clear_metrics,
                args=(model, device_id, firmware),
            )

        self.timers[device_id].start()

    def clear_metrics(self, model, device_id, firmware):
        logger.debug(f"ws90: Clearing metrics for device {device_id}")

        for _, m in self.metrics.items():
            m.remove(device_id)
        for _, m in self.model_info.items():
            m.remove(device_id)


class WS90Reader(threading.Thread):
    def __init__(self, cmd, device_ids, signal, future):
        super().__init__()

        self.cmd = self._parse_cmd(cmd)
        self.device_ids = device_ids
        self.signal = sig
        self.future = future

        if len(self.device_ids) == 0:
            logger.info("ws90: Listening messages from all devices")
        else:
            logger.info(f"ws90: Listening messages from devices with ids: {self.device_ids}")

    def _parse_cmd(self, cmd):
        return cmd.split()

    async def _read_stream(self, stream, callback):
        while True:
            line = await stream.readline()
            if not line:
                break
            callback(line.decode("utf-8"))

    async def background_job(self):
        logger.debug(f"ws90: Will listen for data using {self.cmd}")
        logger.info("ws90: Listening for data")
        p = await asyncio.create_subprocess_exec(self.cmd[0], *self.cmd[1:], stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        await asyncio.gather(
            self._read_stream(p.stdout, self.read_stdout),
            self._read_stream(p.stderr, self.read_stderr),
        )

        await p.wait()
        logger.debug(f"ws90: rtl_433 exited with code {p.returncode}")

    def run(self):
        try:
            asyncio.run(self.background_job())
            self.future.set_result(True)
        except Exception as e:
            self.future.set_exception(e)

    def read_stdout(self, line):
        try:
            data = json.loads(line)
            self.process_data(data)
        except json.JSONDecodeError:
            logger.error(f"ws90: Failed to parse rtl_433's json output: {line.strip()}")

    def read_stderr(self, line):
        line = line.strip()
        if line != "":
            logger.warning(f"rtl_433: {line}")

    def process_data(self, data):
        if data.get("model", None) != "Fineoffset-WS90":
            return

        if "id" not in data:
            logger.error(f"ws90: No ID in received data: {data}")
            return

        device_id = data["id"]
        if len(self.device_ids) > 0 and device_id not in self.device_ids:
            logger.debug(f"ws90: Received message from ID {data['id']} (0x{data['id']:x}), expected one of {self.device_ids}. Ignoring.")
            return

        logger.debug(f"ws90: Received data {data}")
        self.signal.send(data)


def as_number(value, allow_hex=False):
    try:
        return int(value)
    except ValueError:
        pass

    try:
        if allow_hex and value.startswith("0x"):
            return int(value, 16)
    except ValueError:
        pass
    raise docopt.DocoptExit(f"Invalid number: {value}")


class PrometheusServer(threading.Thread):
    def __init__(self, port):
        super().__init__()
        self.port = port

    def run(self):
        logger.info("prometheus: Starting HTTP server on port %s", self.port)
        prom.start_http_server(self.port, addr="::")


FIELDS = [
    ("temperature_C", "ws90_temperature_celsius", "Temperature in Celsius", None),
    ("humidity", "ws90_humidity_ratio", "Humidity in percent", None),
    ("battery_ok", "ws90_battery_ratio", "Battery percent", None),
    ("battery_mV", "ws90_battery_volts", "Battery voltage", lambda x: x / 1000),  # mV to V
    ("supercap_V", "ws90_supercap_volts", "Supercap voltage", None),
    ("wind_dir_deg", "ws90_wind_dir_degrees", "Wind direction in degrees", None),
    ("wind_avg_m_s", "ws90_wind_avg_speed", "Wind speed in m/s", None),
    ("wind_max_m_s", "ws90_wind_gust_speed", "Wind gust speed in m/s", None),
    ("uvi", "ws90_uvi", "UV index", None),
    ("light_lux", "ws90_light_lux", "Light in lux", None),
    ("rain_mm", "ws90_rain_m", "Total rain", lambda x: x / 1000),  # mm to m
    ("rain_start", "ws90_rain_start", "Rain start info", None),
]
FIELDS_MODEL = [
    ("ws90_model", "Model information", ["firmware", "model"]),
]

if __name__ == "__main__":
    args = docopt.docopt(__doc__, version="WS90 Prometheus exporter")

    init_logging(args["--log"], args["--log-level"])

    sig = blinker.signal("data-received")

    p = PrometheusPublisher(int(args["--clear"]), FIELDS, FIELDS_MODEL)
    sig.connect(p.data_callback)

    exc_watcher = concurrent.futures.Future()
    thr_reader = WS90Reader(args["--cmd"], list(map(lambda x: as_number(x, allow_hex=True), args["--id"])), sig, exc_watcher)
    thr_reader.start()

    thr_prom_server = PrometheusServer(as_number(args["--port"]))
    thr_prom_server.start()

    try:
        exc_watcher.result()
    except Exception as e:
        logger.exception(f"Exception in background reader thread: {e}")

    thr_reader.join()
    thr_prom_server.join()
