import datetime
import logging
import requests
import urllib.parse

from . import stations

logger = logging.getLogger(__name__)


class VictoriaMetricsPublisher:
    def __init__(self, vmbaseurl, registry=stations.STATIONS):
        self.vmbaseurl = vmbaseurl
        self.registry = registry

    def _post(self, labels, data, format):
        resp = requests.post(
            urllib.parse.urljoin(self.vmbaseurl, "/api/v1/import/csv"),
            params={
                "format": ",".join(format),
                "extra_label": labels,
            },
            data=",".join(map(str, data)).strip(),
        )
        resp.raise_for_status()
        logger.debug(f"rtl433: Posted data to VictoriaMetrics ({labels}): {data} (response: {resp.status_code})")

    def _construct_metrics(self, data, station, dt):
        columns = ["1:time:unix_s"]
        csv_line = [int(dt.timestamp())]

        for i, field in enumerate(station.fields, 2):
            columns.append(f"{i}:metric:{stations.METRICS[field.metric_key].name}")
            csv_line.append(field.value(data))

        return csv_line, columns

    def _construct_info(self, data, station, dt):
        name = f"{stations.INFO_METRIC_NAME}_info"
        columns = ["1:time:unix_s", f"2:metric:{name}"]
        csv_line = [int(dt.timestamp()), 1]

        for i, key in enumerate(station.info_keys, 3):
            columns.append(f"{i}:label:{key}")
            csv_line.append(data[key])

        return csv_line, columns

    def data_callback(self, data):
        station = self.registry[data["model"]]
        dt = datetime.datetime.strptime(data["time"], "%Y-%m-%d %H:%M:%S")
        extra_label = f"id={data['id']},model={data['model']}"

        self._post(extra_label, *self._construct_metrics(data, station, dt))
        self._post(extra_label, *self._construct_info(data, station, dt))
