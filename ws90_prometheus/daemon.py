import blinker
import concurrent.futures
import logging

from .publish_prom import PrometheusPublisher, PrometheusServer
from .publish_vm import VictoriaMetricsPublisher
from .rtl_reader import WS90Reader

logger = logging.getLogger(__name__)


FIELDS = [
    ("temperature_C", "ws90_temperature_celsius", "Temperature in Celsius", None),
    ("humidity", "ws90_humidity_ratio", "Humidity in percent", None),
    ("battery_ok", "ws90_battery_ratio", "Battery percent", None),
    ("battery_mV", "ws90_battery_volts", "Battery voltage", lambda x: x / 1000),  # mV to V
    ("supercap_V", "ws90_supercap_volts", "Supercap voltage", None),
    ("wind_dir_deg", "ws90_wind_dir_degrees", "Wind direction in degrees", None),
    ("wind_avg_m_s", "ws90_wind_avg_speed", "Wind speed in m/s", None),
    ("wind_max_m_s", "ws90_wind_gust_speed", "Wind gust speed in m/s", None),
    ("uvi", "ws90_uvi", "UV index", None),
    ("light_lux", "ws90_light_lux", "Light in lux", None),
    ("rain_mm", "ws90_rain_m", "Total rain", lambda x: x / 1000),  # mm to m
    ("rain_start", "ws90_rain_start", "Rain start info", None),
]
FIELDS_MODEL = [
    ("ws90_model", "Model information", ["firmware", "model"]),
]


class WS90PromDaemon:
    def __init__(
        self,
        rtl_cmd,
        device_ids,
        prom_clear_interval,
        prom_port,
        vm_baseurl,
    ):
        self.sig = blinker.signal("data-received")

        self.pub_prom = PrometheusPublisher(prom_clear_interval, FIELDS, FIELDS_MODEL)
        self.sig.connect(self.pub_prom.data_callback)

        if vm_baseurl is not None:
            self.pub_vm = VictoriaMetricsPublisher(vm_baseurl, FIELDS, FIELDS_MODEL)
            self.sig.connect(self.pub_vm.data_callback)

        self.exc_watcher = concurrent.futures.Future()
        self.thr_reader = WS90Reader(rtl_cmd, device_ids, self.sig, self.exc_watcher)
        self.thr_prom_server = PrometheusServer(prom_port)

    def run(self):
        self.thr_reader.start()
        self.thr_prom_server.start()

        try:
            self.exc_watcher.result()
        except Exception as e:
            logger.exception(f"Exception in background reader thread: {e}")

        self.thr_reader.join()
        self.thr_prom_server.join()
