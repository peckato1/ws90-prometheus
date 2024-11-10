#!/usr/bin/env python

"""
Fake data generator for WS90 Prometheus exporter

Usage:
    fake.py [--id=<id>]... [--interval=<interval>] [--count=<count>]
    fake.py --help

Options:
    --id=<id>               Device IDs to generate data for. If none are given, generate random IDs every time.
    --interval=<interval>   Interval between data points in seconds [default: 2]
    --count=<count>         Number of data points to generate. 0 means infinite. [default: 0]
    --help                  Show this screen
"""

import dataclasses
import datetime
import docopt
import json
import random
import time


@dataclasses.dataclass
class Data:
    time: str
    model: str
    id: int
    battery_mV: int
    battery_ok: float
    temperature_C: float
    humidity: int
    wind_dir_deg: int
    wind_avg_m_s: float
    wind_max_m_s: float
    uvi: float
    light_lux: float
    flags: int
    rain_mm: float
    supercap_V: float
    firmware: str
    data: str
    mic: str


def random_data(device_ids):
    device_id = random.choice(device_ids) if device_ids else random.randint(0, 0xffffff)
    battery_mv = random.randint(1000, 3000)

    return Data(
        time=datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        model='Fineoffset-WS90',
        id=device_id,
        light_lux=round(random.uniform(0, 200), 1),
        battery_mV=battery_mv,
        battery_ok=round((0 if battery_mv < 1400 else (battery_mv - 1400) / 16) / 100, 1),
        temperature_C=round(random.uniform(-40, 60), 1),
        humidity=random.randint(1, 100),
        wind_dir_deg=random.randint(0, 360),
        wind_avg_m_s=round(random.uniform(0, 40), 1),
        wind_max_m_s=round(random.uniform(0, 40), 1),
        uvi=random.randint(1, 16),
        flags=random.randint(0, 0xff),
        rain_mm=round(random.uniform(0, 10000), 0),
        supercap_V=round(random.randint(0, 0x3F) / 10, 1),
        firmware='126',
        data='3fff000000------0000fe8fde0000',
        mic='CRC'
    )


def run(device_ids, count, interval):
    i = 0
    while count == 0 or i < count:
        data = random_data(device_ids)
        print(json.dumps(dataclasses.asdict(data)))
        time.sleep(interval)
        i += 1


if __name__ == '__main__':
    args = docopt.docopt(__doc__, version='Fake data generator for WS90 Prometheus exporter')
    run(args['--id'], int(args['--count']), int(args['--interval']))
