# rtl433-meteo

Reads data from RF weather stations using [rtl_433](https://github.com/merbanan/rtl_433)
(RTL-SDR) and pushes it to [VictoriaMetrics](https://victoriametrics.com/) via its
CSV import API.

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
2. List any model-specific text keys (like `firmware`/`channel`) in `info_keys`.

No changes to the reader or publisher are needed.

## Usage

```console
$ rtl433-meteo <vmbaseurl> [--id=<id>]... [--cmd=<cmd>] [--log-level=<level>]
```

The VictoriaMetrics base URL is required — every reading is pushed to its
`/api/v1/import/csv` endpoint. By default the tool runs
`rtl_433 -f 868.3M -F json`; use `--id` (repeatable, decimal or `0x`-hex)
to restrict to specific device IDs. See `rtl433-meteo --help` for all options.

## Development

Run against the fake data generator without any radio hardware (point it at a local
VictoriaMetrics, or any HTTP endpoint that accepts the CSV import POST):

```console
$ rtl433-meteo http://localhost:8428 --cmd "python fake/fake.py --model Vevor-7in1" --log-level debug
```

`fake/fake.py --model {Fineoffset-WS90,Vevor-7in1}` emits synthetic rtl_433 JSON lines.

Run the tests with:

```console
$ uv run pytest
```

## Installation

`rtl433-meteo` is a standard Python package. How you install it decides where the
`rtl433-meteo` executable ends up — and that path is what the service units call, so
the two must agree. Find the installed path any time with `command -v rtl433-meteo`.

### Isolated virtualenv (recommended)

Keeps the dependencies off the system Python and sidesteps the "externally managed
environment" (PEP 668) error on Arch/Alpine/Debian:

```console
# python -m venv /opt/rtl433-meteo
# /opt/rtl433-meteo/bin/pip install .
```

The executable is then `/opt/rtl433-meteo/bin/rtl433-meteo`. Point the service at it
(systemd: edit `ExecStart`; OpenRC: set `command=` in `/etc/conf.d/rtl433-meteo`),
or symlink it so the default `/usr/bin` path works:

```console
# ln -s /opt/rtl433-meteo/bin/rtl433-meteo /usr/bin/rtl433-meteo
```

### System-wide

```console
# pip install .        # add --break-system-packages on PEP 668 distros
```

Scripts land in the system bin — `/usr/bin` or `/usr/local/bin` depending on the
distro; check with `command -v rtl433-meteo`.

### Logging to the systemd journal

`--log=systemd` needs the optional `systemd` extra: `pip install .[systemd]`. It
pulls in `systemd-python`, which requires libsystemd at build time, so only install
it on systemd hosts. Plain installs and the OpenRC service (which logs to a file)
don't need it.

## Deployment

The service units below call `/usr/bin/rtl433-meteo` by default — adjust the path
to match your install (see above).

**systemd** — [`rtl433-meteo.service`](rtl433-meteo.service):

```console
# cp rtl433-meteo.service /etc/systemd/system/
# systemctl enable --now rtl433-meteo
```

**OpenRC** — [`rtl433-meteo.initd`](rtl433-meteo.initd) + [`rtl433-meteo.confd`](rtl433-meteo.confd):

```console
# install -m0755 rtl433-meteo.initd /etc/init.d/rtl433-meteo
# install -m0644 rtl433-meteo.confd /etc/conf.d/rtl433-meteo
# $EDITOR /etc/conf.d/rtl433-meteo      # set vmbaseurl, options, optional user
# rc-update add rtl433-meteo default
# rc-service rtl433-meteo start
```

The OpenRC service stops with SIGINT so the `rtl_433` child is shut down cleanly.
Both units default to `http://localhost:8428`; change it for a remote VictoriaMetrics.
