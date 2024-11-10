#!/usr/bin/env python

"""
WS90 Prometheus exporter

Usage:
    ws90-prometheus.py [--id=<id>]... [--port=<port>] [--log=<systemd|stdout>] [--log-level=<level>] [--cmd=<cmd>]
    ws90-prometheus.py --help

Options:
    --id=<id>               Device ID. Can be decimal or hex (prefix with 0x). Can specify multiple times. If not specified, all devices are being monitored.
    --port=<port>           Port to listen on [default: 8000]
    --log=<systemd|stderr>  Log to systemd journal or stderr [default: stderr]
    --log-level=<level>     Log level (debug, info, warning, error) [default: info]
    --cmd=<cmd>             Command to run [default: rtl_433 -Y minmax -f 868.3M -F json]
    --help                  Show this screen
"""


import json
import subprocess
import prometheus_client as prom
import threading
import logging
import systemd.journal
import docopt
import sys


logger = logging.getLogger(__name__)


def init_logging(log_type, log_level):
    if log_type == 'systemd':
        logger.addHandler(systemd.journal.JournalHandler())
    elif log_type == 'stderr':
        handler = logging.StreamHandler(sys.stderr)
        formatter = logging.Formatter(fmt='%(asctime)s - %(levelname)8s - %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    else:
        raise docopt.DocoptExit(f'Invalid log type: {log_type}')

    match log_level.lower():
        case 'debug':
            logger.setLevel(logging.DEBUG)
        case 'info':
            logger.setLevel(logging.INFO)
        case 'warning':
            logger.setLevel(logging.WARNING)
        case 'error':
            logger.setLevel(logging.ERROR)
        case _:
            raise docopt.DocoptExit(f'Invalid log level: {log_level}')


class WS90Metrics(threading.Thread):
    def __init__(self, cmd, device_ids):
        super().__init__()

        self.cmd = self._parse_cmd(cmd)
        self.device_ids = device_ids

        if len(self.device_ids) == 0:
            logger.info('ws90: Listening messages from all devices')
        else:
            logger.info(f'ws90: Listening messages from devices with ids: {self.device_ids}')

        self.temp = prom.Gauge('ws90_temperature_celsius', 'Temperature in Celsius', ['id'])
        self.humidity = prom.Gauge('ws90_humidity_ratio', 'Humidity in percent', ['id'])
        self.battery_perc = prom.Gauge('ws90_battery_ratio', 'Battery percent', ['id'])
        self.battery_volt = prom.Gauge('ws90_battery_volts', 'Battery voltage', ['id'])
        self.supercapacitator_volt = prom.Gauge('ws90_supercap_volts', 'Supercap voltage', ['id'])
        self.wind_dir = prom.Gauge('ws90_wind_dir_degrees', 'Wind direction in degrees', ['id'])
        self.wind_avg = prom.Gauge('ws90_wind_avg_speed', 'Wind speed in m/s', ['id'])
        self.wind_gust = prom.Gauge('ws90_wind_gust_speed', 'Wind gust speed in m/s', ['id'])
        self.uvi = prom.Gauge('ws90_uvi', 'UV index', ['id'])
        self.light = prom.Gauge('ws90_light_lux', 'Light in lux', ['id'])
        self.rain_total = prom.Gauge('ws90_rain_m', 'Total rain', ['id'])
        self.model = prom.Info('ws90_model', 'Model description', ['model', 'id', 'firmware'])

    def _parse_cmd(self, cmd):
        return cmd.split()

    def run(self):
        logger.debug(f'ws90: Will listen for data using {self.cmd}')
        logger.info('ws90: Listening for data')
        with subprocess.Popen(self.cmd,
                              stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE,
                              bufsize=1,
                              universal_newlines=True) as p:
            t1 = threading.Thread(
                    target=self.read_stream,
                    args=(p.stdout, self.read_stdout))

            t2 = threading.Thread(
                    target=self.read_stream,
                    args=(p.stderr, self.read_stderr))

            t1.start()
            t2.start()

            t1.join()
            t2.join()

        p.wait()
        logger.debug(f'ws90: rtl_433 exited with code {p.returncode}')

    def read_stdout(self, line):
        try:
            data = json.loads(line)
            self.process_data(data)
        except json.JSONDecodeError:
            logger.error(f"ws90: Failed to parse rtl_433's json output: {line.strip()}")

    def read_stderr(self, line):
        line = line.strip()
        if line != '':
            logger.warning(f'rtl_433: {line}')

    def process_data(self, data):
        if data.get('model', None) != 'Fineoffset-WS90':
            return

        if 'id' not in data:
            logger.error(f'ws90: No ID in received data: {data}')
            return

        device_id = data['id']
        if len(self.device_ids) > 0 and device_id not in self.device_ids:
            logger.debug(f'ws90: Received message from ID {data["id"]} (0x{data["id"]:x}), expected one of {self.device_ids}. Ignoring.')
            return

        logger.debug(f'ws90: Received data {data}')

        self.model.labels(data['model'], data['id'], data['firmware']).info({})

        self.temp.labels(device_id).set(data['temperature_C'])
        self.humidity.labels(device_id).set(data['humidity'])
        self.battery_perc.labels(device_id).set(data['battery_ok'])
        self.battery_volt.labels(device_id).set(data['battery_mV'] / 1000)
        self.supercapacitator_volt.labels(device_id).set(data['supercap_V'])
        self.wind_dir.labels(device_id).set(data['wind_dir_deg'])
        self.wind_avg.labels(device_id).set(data['wind_avg_m_s'])
        self.wind_gust.labels(device_id).set(data['wind_max_m_s'])
        self.uvi.labels(device_id).set(data['uvi'])
        self.light.labels(device_id).set(data['light_lux'])
        self.rain_total.labels(device_id).set(data['rain_mm'] / 1000)

    def read_stream(self, stream, callback):
        try:
            with stream:
                for line in stream:
                    callback(line)
        except ValueError:
            pass


def as_number(value, allow_hex=False):
    try:
        return int(value)
    except ValueError:
        pass

    try:
        if allow_hex and value.startswith('0x'):
            return int(value, 16)
    except ValueError:
        pass
    raise docopt.DocoptExit(f'Invalid number: {value}')


if __name__ == '__main__':
    args = docopt.docopt(__doc__, version='WS90 Prometheus exporter')

    init_logging(args['--log'], args['--log-level'])

    t = WS90Metrics(
            cmd=args['--cmd'],
            device_ids=list(map(lambda x: as_number(x, allow_hex=True), args['--id'])))
    t.start()

    port = as_number(args['--port'])
    logger.info('prometheus: Starting HTTP server on port %s', port)
    prom.start_http_server(port)
