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
    def __init__(self, clear_interval):
        self.clear_interval = clear_interval
        self.timers = dict()

        self.temp = prom.Gauge("ws90_temperature_celsius", "Temperature in Celsius", ["id"])
        self.humidity = prom.Gauge("ws90_humidity_ratio", "Humidity in percent", ["id"])
        self.battery_perc = prom.Gauge("ws90_battery_ratio", "Battery percent", ["id"])
        self.battery_volt = prom.Gauge("ws90_battery_volts", "Battery voltage", ["id"])
        self.supercapacitator_volt = prom.Gauge("ws90_supercap_volts", "Supercap voltage", ["id"])
        self.wind_dir = prom.Gauge("ws90_wind_dir_degrees", "Wind direction in degrees", ["id"])
        self.wind_avg = prom.Gauge("ws90_wind_avg_speed", "Wind speed in m/s", ["id"])
        self.wind_gust = prom.Gauge("ws90_wind_gust_speed", "Wind gust speed in m/s", ["id"])
        self.uvi = prom.Gauge("ws90_uvi", "UV index", ["id"])
        self.light = prom.Gauge("ws90_light_lux", "Light in lux", ["id"])
        self.rain_total = prom.Gauge("ws90_rain_m", "Total rain", ["id"])
        self.model = prom.Info("ws90_model", "Model description", ["model", "id", "firmware"])
        self.last_sync = None

    def data_callback(self, data):
        device_id = data["id"]
        self.model.labels(data["model"], data["id"], data["firmware"]).info({})

        self.temp.labels(device_id).set(data["temperature_C"])
        self.humidity.labels(device_id).set(data["humidity"])
        self.battery_perc.labels(device_id).set(data["battery_ok"])
        self.battery_volt.labels(device_id).set(data["battery_mV"] / 1000)
        self.supercapacitator_volt.labels(device_id).set(data["supercap_V"])
        self.wind_dir.labels(device_id).set(data["wind_dir_deg"])
        self.wind_avg.labels(device_id).set(data["wind_avg_m_s"])
        self.wind_gust.labels(device_id).set(data["wind_max_m_s"])
        self.uvi.labels(device_id).set(data["uvi"])
        self.light.labels(device_id).set(data["light_lux"])
        self.rain_total.labels(device_id).set(data["rain_mm"] / 1000)
        self.set_timer(data["model"], device_id, data["firmware"])

    def set_timer(self, model, device_id, firmware):
        if self.clear_interval == 0:
            return

        if device_id not in self.timers:
            self.timers[device_id] = ResettableTimer(
                self.clear_interval,
                self.clear_metrics,
                args=(
                    model,
                    device_id,
                    firmware,
                ),
            )

        self.timers[device_id].start()

    def clear_metrics(self, model, device_id, firmware):
        logger.debug(f"ws90: Clearing metrics for device {device_id}")

        self.temp.remove(device_id)
        self.humidity.remove(device_id)
        self.battery_perc.remove(device_id)
        self.battery_volt.remove(device_id)
        self.supercapacitator_volt.remove(device_id)
        self.wind_dir.remove(device_id)
        self.wind_avg.remove(device_id)
        self.wind_gust.remove(device_id)
        self.uvi.remove(device_id)
        self.light.remove(device_id)
        self.rain_total.remove(device_id)
        self.model.remove(model, device_id, firmware)


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


if __name__ == "__main__":
    args = docopt.docopt(__doc__, version="WS90 Prometheus exporter")

    init_logging(args["--log"], args["--log-level"])

    sig = blinker.signal("data-received")

    p = PrometheusPublisher(int(args["--clear"]))
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
