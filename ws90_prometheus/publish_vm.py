import datetime
import logging
import requests
import urllib.parse

logger = logging.getLogger(__name__)


class VictoriaMetricsPublisher:
    def __init__(self, vmbaseurl, metrics_data, model_data):
        self.vmbaseurl = vmbaseurl
        self.metrics_data = metrics_data
        self.model_data = model_data

    def _post(self, device_id, data, format):
        resp = requests.post(
            urllib.parse.urljoin(self.vmbaseurl, "/api/v1/import/csv"),
            params={
                "format": ",".join(format),
                "extra_label": f"id={device_id}",
            },
            data=",".join(map(str, data)).strip(),
        )
        resp.raise_for_status()
        logger.debug(f"ws90: Posted data to VictoriaMetrics for device {device_id}: {data} (response: {resp.status_code})")

    def _construct_metrics(self, data, device_id, dt):
        columns = ["1:time:unix_s"]
        csv_line = [int(dt.timestamp())]

        for i, (json_key, name, _, postprocess) in enumerate(self.metrics_data, 2):
            value = data[json_key] if postprocess is None else postprocess(data[json_key])
            columns.append(f"{i}:metric:{name}")
            csv_line.append(value)
            break

        return csv_line, columns

    def _construct_modelinfo(self, data, device_id, dt, name, keys):
        columns = ["1:time:unix_s", f"2:metric:{name}_info"]
        csv_line = [int(dt.timestamp()), 1]

        for i, key in enumerate(keys, 3):
            columns.append(f"{i}:label:{name}")
            csv_line.append(data[key])

        return csv_line, columns

    def data_callback(self, data):
        device_id = data["id"]
        dt = datetime.datetime.strptime(data["time"], "%Y-%m-%d %H:%M:%S")

        self._post(device_id, *self._construct_metrics(data, device_id, dt))
        for name, _, keys in self.model_data:
            self._post(device_id, *self._construct_modelinfo(data, device_id, dt, name, keys))
