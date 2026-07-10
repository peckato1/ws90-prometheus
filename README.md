# rtl433-meteo

Reads data from RF weather stations using [rtl_433](https://github.com/merbanan/rtl_433)
(RTL-SDR) and exposes it for Prometheus scraping, optionally also pushing it to
VictoriaMetrics.

## Supported stations

Stations are configuration, not code — each is an entry in
[`rtl433_meteo/stations.py`](rtl433_meteo/stations.py). Currently supported:

| rtl_433 model     | Notes                                                        |
| ----------------- | ------------------------------------------------------------ |
| `Fineoffset-WS90` | Temperature, humidity, wind, rain, UV, light, battery, supercap, firmware |
| `Vevor-7in1`      | Temperature, humidity, wind, rain, UV, light, battery, channel |

Metrics are shared across stations under generic `meteo_*` names and disambiguated
by the `model` and `id` labels. Per-station unit differences are normalized (wind is
always exported in m/s, rain in metres), so the same metric is comparable across
stations. Model-specific details (firmware, channel) are carried by the `meteo_info`
metric.

### Adding a station

1. Add a `Station(...)` entry to `STATIONS` in `rtl433_meteo/stations.py`, mapping the
   station's rtl_433 JSON keys to the shared metrics (add a `transform` for any unit
   conversion, and a new `Metric` to `METRICS` only if the quantity is genuinely new).
2. List any model-specific text keys (like `firmware`/`channel`) in `info_keys`, and
   add them to `INFO_KEYS` if not already present.

No changes to the reader or publishers are needed.

## Usage

```console
$ rtl433-meteo --help
```

By default it runs `rtl_433 -Y minmax -f 868.3M -F json` and serves metrics on
`:8000`. Pass `--vmbaseurl=<url>` to also push to VictoriaMetrics, and `--id` (repeatable,
decimal or `0x`-hex) to restrict to specific device IDs.

## Development

Run against the fake data generator without any radio hardware:

```console
$ rtl433-meteo --cmd "python fake/fake.py --model Vevor-7in1" --log-level debug
$ curl -s localhost:8000/metrics | grep meteo_
```

`fake/fake.py --model {Fineoffset-WS90,Vevor-7in1}` emits synthetic rtl_433 JSON lines.

Run the tests with:

```console
$ uv run pytest
```

## Deployment

A systemd unit is provided in [`rtl433-meteo.service`](rtl433-meteo.service). Installing
the package (e.g. `pip install .`) provides the `rtl433-meteo` console script.
