"""rtl433-meteo -- export rtl_433 weather-station metrics to Prometheus/VictoriaMetrics.

Usage:
    rtl433-meteo
        [--id=<id>]...
        [--port=<port>]
        [--vmbaseurl=<url>]
        [--clear=<clear>]
        [--log=<systemd|stderr>]
        [--log-level=<level>]
        [--cmd=<cmd>]
    rtl433-meteo --help

Options:
    --id=<id>               Device ID. Can be decimal or hex (prefix with 0x). Can specify multiple times. If not specified, all devices are being monitored.
    --port=<port>           Port to listen on [default: 8000]
    --vmbaseurl=<url>       VictoriaMetrics base URL. If not specified, VictoriaMetrics publishing is disabled.
    --log-level=<level>     Log level (debug, info, warning, error) [default: info]
    --clear=<clear>         Remove metrics for device after <clear> seconds. 0 for never. Useful for purging outdated metrics when the receiver stops receiving new data for a device. [default: 120]
    --log=<systemd|stderr>  Log to systemd journal or stderr [default: stderr]
    --cmd=<cmd>             Command to run [default: rtl_433 -Y minmax -f 868.3M -F json]
    --help                  Show this screen
"""

import docopt
import logging
import sys

from .daemon import MeteoExporterDaemon

logger = logging.getLogger(__name__)


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


def init_logging(log_type, log_level):
    root_logger = logging.getLogger()

    if log_type == "systemd":
        try:
            import systemd.journal

            handler = systemd.journal.JournalHandler()
        except ImportError:
            raise ImportError("systemd logging requested, but systemd.journal module not found")
    elif log_type == "stderr":
        handler = logging.StreamHandler(sys.stderr)
        formatter = logging.Formatter(fmt="%(asctime)s - %(levelname)8s - %(message)s")
        handler.setFormatter(formatter)
    else:
        raise docopt.DocoptExit(f"Invalid log type: {log_type}")

    match log_level.lower():
        case "debug":
            log_level = logging.DEBUG
        case "info":
            log_level = logging.INFO
        case "warning":
            log_level = logging.WARNING
        case "error":
            log_level = logging.ERROR
        case _:
            raise docopt.DocoptExit(f"Invalid log level: {log_level}")

    root_logger.addHandler(handler)
    root_logger.setLevel(log_level)


def main():
    args = docopt.docopt(__doc__, version="rtl433-meteo exporter")

    init_logging(args["--log"], args["--log-level"])

    device_ids = [as_number(x, allow_hex=True) for x in args["--id"]]
    daemon = MeteoExporterDaemon(
        args["--cmd"],
        device_ids,
        int(args["--clear"]),
        int(args["--port"]),
        args["--vmbaseurl"],
    )
    daemon.run()


if __name__ == "__main__":
    main()
