#!/usr/bin/env python

"""
WS90 Prometheus exporter

Usage:
    ws90-prometheus.py --id=<id> [--port=<port>]
    ws90-prometheus.py --help

Options:
    --id=<id>       Device ID. Can be decimal or hex (prefix with 0x)
    --port=<port>   Port to listen on [default: 8000]
    --help          Show this screen
"""


import json
import subprocess
import prometheus_client as prom
import threading
import logging
import systemd.journal
import docopt


logger = logging.getLogger(__name__)
logger.addHandler(systemd.journal.JournalHandler())
logger.setLevel(logging.DEBUG)


class WS90Metrics(threading.Thread):
    def __init__(self, device_id):
        super().__init__()

        logger.info(f'Initializing WS90Metrics with device ID {device_id} (0x{device_id:x})')
        self.device_id = device_id

        self.temp = prom.Gauge('ws90_temperature_celsius', 'Temperature in Celsius')
        self.humidity = prom.Gauge('ws90_humidity_ratio', 'Humidity in percent')
        self.battery_perc = prom.Gauge('ws90_battery_ratio', 'Battery percent')
        self.battery_volt = prom.Gauge('ws90_battery_volts', 'Battery voltage')
        self.supercapacitator_volt = prom.Gauge('ws90_supercap_volts', 'Supercap voltage')
        self.wind_dir = prom.Gauge('ws90_wind_dir_degrees', 'Wind direction in degrees')
        self.wind_avg = prom.Gauge('ws90_wind_avg_speed', 'Wind speed in m/s')
        self.wind_gust = prom.Gauge('ws90_wind_gust_speed', 'Wind gust speed in m/s')
        self.uvi = prom.Gauge('ws90_uvi', 'UV index')
        self.light = prom.Gauge('ws90_light_lux', 'Light in lux')
        self.rain_total = prom.Gauge('ws90_rain_m', 'Total rain')
        self.model = prom.Info('ws90_model', 'Model description')

    def run(self):
        cmd = ['rtl_433', '-Y', 'minmax', '-f', '868.3M', '-F', 'json']
        logger.info('Started WS90 Prometheus exporter')
        logger.debug(f'Reading using command {cmd}')
        with subprocess.Popen(cmd,
                              stdout=subprocess.PIPE,
                              stderr=subprocess.DEVNULL,
                              bufsize=1,
                              universal_newlines=True) as p:
            for line in p.stdout:
                data = json.loads(line)
                logger.debug(f'Received data {data}')

                if data.get('model', None) != 'Fineoffset-WS90':
                    continue

                if data.get('id', None) != self.device_id:
                    logger.debug(f'Received message from ID {data["id"]} (0x{data["id"]:x}), expected {self.device_id}')
                    continue

                self.model.info({
                    'model': data['model'],
                    'id': str(data['id']),
                    'firmware': str(data['firmware'])})

                self.temp.set(data['temperature_C'])
                self.humidity.set(data['humidity'])
                self.battery_perc.set(data['battery_ok'])
                self.battery_volt.set(data['battery_mV'] / 1000)
                self.supercapacitator_volt.set(data['supercap_V'])
                self.wind_dir.set(data['wind_dir_deg'])
                self.wind_avg.set(data['wind_avg_m_s'])
                self.wind_gust.set(data['wind_max_m_s'])
                self.uvi.set(data['uvi'])
                self.light.set(data['light_lux'])
                self.rain_total.set(data['rain_mm'] / 1000)

        p.wait()


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

    t = WS90Metrics(as_number(args['--id'], allow_hex=True))
    t.start()

    port = as_number(args['--port'])
    logger.info('Starting Prometheus HTTP server on port %s', port)
    prom.start_http_server(port)
