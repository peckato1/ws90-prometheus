#!/usr/bin/env python

"""
Fake data generator for the rtl433-meteo exporter

Usage:
    fake.py [--model=<model>] [--id=<id>]... [--interval=<interval>] [--count=<count>]
    fake.py --help

Options:
    --model=<model>         Station model to emulate: Fineoffset-WS90 or Vevor-7in1 [default: Fineoffset-WS90]
    --id=<id>               Device IDs to generate data for. If none are given, generate random IDs every time.
    --interval=<interval>   Interval between data points in seconds [default: 2]
    --count=<count>         Number of data points to generate. 0 means infinite. [default: 0]
    --help                  Show this screen
"""

import datetime
import docopt
import json
import random
import time


def _now():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _device_id(device_ids):
    return random.choice(device_ids) if device_ids else random.randint(0, 0xFFFFFF)


def ws90_data(device_ids):
    battery_mv = random.randint(1000, 3000)
    return {
        "time": _now(),
        "model": "Fineoffset-WS90",
        "id": _device_id(device_ids),
        "battery_mV": battery_mv,
        "battery_ok": round((0 if battery_mv < 1400 else (battery_mv - 1400) / 16) / 100, 1),
        "temperature_C": round(random.uniform(-40, 60), 1),
        "humidity": random.randint(1, 100),
        "wind_dir_deg": random.randint(0, 360),
        "wind_avg_m_s": round(random.uniform(0, 40), 1),
        "wind_max_m_s": round(random.uniform(0, 40), 1),
        "uvi": random.randint(1, 16),
        "light_lux": round(random.uniform(0, 200), 1),
        "flags": random.randint(0, 0xFF),
        "rain_mm": round(random.uniform(0, 10000), 0),
        "rain_start": random.randint(0, 1),
        "supercap_V": round(random.randint(0, 0x3F) / 10, 1),
        "firmware": "126",
        "data": "3fff000000------0000fe8fde0000",
        "mic": "CRC",
    }


def vevor_data(device_ids):
    return {
        "time": _now(),
        "model": "Vevor-7in1",
        "id": _device_id(device_ids),
        "channel": random.randint(1, 3),
        "battery_ok": round(random.uniform(0, 1), 1),
        "temperature_C": round(random.uniform(-40, 60), 1),
        "humidity": random.randint(1, 100),
        "wind_dir_deg": random.randint(0, 360),
        "wind_avg_km_h": round(random.uniform(0, 140), 1),
        "wind_max_km_h": round(random.uniform(0, 140), 1),
        "uvi": random.randint(1, 16),
        "light_lux": round(random.uniform(0, 200), 1),
        "rain_mm": round(random.uniform(0, 10000), 0),
        "mic": "CRC",
    }


GENERATORS = {
    "Fineoffset-WS90": ws90_data,
    "Vevor-7in1": vevor_data,
}


def run(model, device_ids, count, interval):
    generator = GENERATORS[model]
    i = 0
    while count == 0 or i < count:
        time.sleep(interval)
        print(json.dumps(generator(device_ids)), flush=True)
        i += 1


if __name__ == "__main__":
    args = docopt.docopt(__doc__, version="Fake data generator for rtl433-meteo")
    model = args["--model"]
    if model not in GENERATORS:
        raise docopt.DocoptExit(f"Unknown model: {model}. Choose one of {', '.join(GENERATORS)}")
    run(model, [int(x) for x in args["--id"]], int(args["--count"]), int(args["--interval"]))
