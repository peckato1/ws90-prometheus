import logging
import prometheus_client as prom
import threading

from .resettable_timer import ResettableTimer
from . import stations

logger = logging.getLogger(__name__)


class PrometheusPublisher:
    def __init__(self, clear_interval, registry=stations.STATIONS, prom_registry=None):
        self.clear_interval = clear_interval
        self.registry = registry
        self.timers = dict()

        # A dedicated CollectorRegistry can be injected for tests; production uses
        # the default global registry that prometheus_client's HTTP server exposes.
        prom_registry = prom_registry if prom_registry is not None else prom.REGISTRY

        # Generic gauges, registered once and shared by every station. Each series
        # is identified by the (model, id) label pair.
        self.metrics = {
            key: prom.Gauge(metric.name, metric.description, stations.LABELS, registry=prom_registry)
            for key, metric in stations.METRICS.items()
        }
        self.info = prom.Info(stations.INFO_METRIC_NAME, stations.INFO_METRIC_DESC, stations.LABELS, registry=prom_registry)

    def data_callback(self, data):
        station = self.registry[data["model"]]
        labels = (data["model"], data["id"])

        self.info.labels(*labels).info(self._info_values(data, station))
        for field in station.fields:
            self.metrics[field.metric_key].labels(*labels).set(field.value(data))

        self.set_timer(labels)

    def _info_values(self, data, station):
        # Fill the fixed union of info keys, blanking the ones this station lacks,
        # so every series of the info metric carries a consistent label set.
        provided = {key: str(data[key]) for key in station.info_keys}
        return {key: provided.get(key, "") for key in stations.INFO_KEYS}

    def set_timer(self, labels):
        if self.clear_interval == 0:
            return

        if labels not in self.timers:
            self.timers[labels] = ResettableTimer(
                self.clear_interval,
                self.clear_metrics,
                args=(labels,),
            )

        self.timers[labels].start()

    def clear_metrics(self, labels):
        logger.debug(f"rtl433: Clearing metrics for device {labels}")

        for metric in self.metrics.values():
            try:
                metric.remove(*labels)
            except KeyError:
                pass
        try:
            self.info.remove(*labels)
        except KeyError:
            pass


class PrometheusServer(threading.Thread):
    def __init__(self, port):
        super().__init__()
        self.port = port

    def run(self):
        logger.info("prometheus: Starting HTTP server on port %s", self.port)
        prom.start_http_server(self.port, addr="::")
