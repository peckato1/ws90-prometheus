#!/usr/bin/env python

import json
import subprocess
import prometheus_client as prom
import threading
import logging
import systemd.journal


logger = logging.getLogger(__name__)
logger.addHandler(systemd.journal.JournalHandler())
logger.setLevel(logging.DEBUG)


class WS90Metrics(threading.Thread):
    def __init__(self):
        super().__init__()

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


if __name__ == '__main__':
    t = WS90Metrics()
    t.start()

    logger.info('Starting Prometheus HTTP server')
    prom.start_http_server(8000)
