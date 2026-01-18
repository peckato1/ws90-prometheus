import logging
import prometheus_client as prom
import threading

from .resettable_timer import ResettableTimer

logger = logging.getLogger(__name__)


class PrometheusPublisher:
    def __init__(self, clear_interval, metrics_data, model_data):
        self.clear_interval = clear_interval
        self.timers = dict()

        self.metrics = dict()
        self.postprocess = dict()
        for json_key, name, desc, postprocess in metrics_data:
            self.metrics[json_key] = prom.Gauge(name, desc, ["id"])

            if postprocess is not None:
                self.postprocess[json_key] = postprocess

        self.model_info = dict()
        self.model_keys = dict()
        for name, desc, keys in model_data:
            self.model_info[name] = prom.Info(name, desc, ["id"])
            self.model_keys[name] = keys

        self.last_sync = None

    def _postprocess(self, data, key):
        if key in self.postprocess:
            return self.postprocess[key](data[key])
        return data[key]

    def data_callback(self, data):
        device_id = data["id"]
        for k, model_info in self.model_info.items():
            model_info.labels(device_id).info({k: data[k] for k in self.model_keys[k]})

        for k, v in self.metrics.items():
            v.labels(device_id).set(self._postprocess(data, k))

        self.set_timer(data["model"], device_id, data["firmware"])

    def set_timer(self, model, device_id, firmware):
        if self.clear_interval == 0:
            return

        if device_id not in self.timers:
            self.timers[device_id] = ResettableTimer(
                self.clear_interval,
                self.clear_metrics,
                args=(model, device_id, firmware),
            )

        self.timers[device_id].start()

    def clear_metrics(self, model, device_id, firmware):
        logger.debug(f"ws90: Clearing metrics for device {device_id}")

        for _, m in self.metrics.items():
            m.remove(device_id)
        for _, m in self.model_info.items():
            m.remove(device_id)


class PrometheusServer(threading.Thread):
    def __init__(self, port):
        super().__init__()
        self.port = port

    def run(self):
        logger.info("prometheus: Starting HTTP server on port %s", self.port)
        prom.start_http_server(self.port, addr="::")
