import blinker
import concurrent.futures
import logging
import signal

from .publish_vm import VictoriaMetricsPublisher
from .rtl_reader import RtlReader
from . import stations

logger = logging.getLogger(__name__)


class MeteoExporterDaemon:
    def __init__(
        self,
        rtl_cmd,
        device_ids,
        vm_baseurl,
        registry=stations.STATIONS,
    ):
        self.sig = blinker.signal("data-received")

        self.pub_vm = VictoriaMetricsPublisher(vm_baseurl, registry)
        self.sig.connect(self.pub_vm.data_callback)

        self.exc_watcher = concurrent.futures.Future()
        self.thr_reader = RtlReader(rtl_cmd, registry.keys(), device_ids, self.sig, self.exc_watcher)

    def run(self):
        signal.signal(signal.SIGINT, lambda sig, frame: self.thr_reader.terminate_subprocess())

        self.thr_reader.start()

        try:
            self.exc_watcher.result()
        except Exception as e:
            logger.exception(f"Exception in background reader thread: {e}")

        self.thr_reader.join()
