import asyncio
import json
import logging
import os
import signal
import threading

logger = logging.getLogger(__name__)


class RtlReader(threading.Thread):
    """Runs the rtl_433 subprocess and dispatches messages of known models."""

    def __init__(self, cmd, models, device_ids, signal, future):
        super().__init__()

        self.cmd = self._parse_cmd(cmd)
        self.models = set(models)
        self.device_ids = device_ids
        self.signal = signal
        self.future = future

        logger.info("rtl433: Listening for models: %s", ", ".join(sorted(self.models)))
        if len(self.device_ids) == 0:
            logger.info("rtl433: Listening messages from all devices")
        else:
            logger.info(f"rtl433: Listening messages from devices with ids: {self.device_ids}")

    def _parse_cmd(self, cmd):
        return cmd.split()

    def terminate_subprocess(self):
        if self.p.returncode is None:
            logger.debug("rtl433: Terminating rtl_433 subprocess")
            os.killpg(os.getpgid(self.p.pid), signal.SIGTERM)

    async def _read_stream(self, stream, callback):
        while True:
            line = await stream.readline()
            if not line:
                break
            callback(line.decode("utf-8"))

    async def background_job(self):
        logger.debug(f"rtl433: Will listen for data using {self.cmd}")
        logger.info("rtl433: Listening for data")
        self.p = await asyncio.create_subprocess_exec(self.cmd[0], *self.cmd[1:], stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        await asyncio.gather(
            self._read_stream(self.p.stdout, self.read_stdout),
            self._read_stream(self.p.stderr, self.read_stderr),
        )

        rc = await self.p.wait()
        self.future.set_result(rc)
        logger.debug(f"rtl433: rtl_433 exited with code {self.p.returncode}")

    def run(self):
        try:
            asyncio.run(self.background_job())
        except Exception as e:
            self.future.set_exception(e)

    def read_stdout(self, line):
        try:
            data = json.loads(line)
            self.process_data(data)
        except json.JSONDecodeError:
            logger.error(f"rtl433: Failed to parse rtl_433's json output: {line.strip()}")

    def read_stderr(self, line):
        line = line.strip()
        if line != "":
            logger.warning(f"rtl_433: {line}")

    def process_data(self, data):
        if data.get("model", None) not in self.models:
            return

        if "id" not in data:
            logger.error(f"rtl433: No ID in received data: {data}")
            return

        device_id = data["id"]
        if len(self.device_ids) > 0 and device_id not in self.device_ids:
            logger.debug(f"rtl433: Received message from ID {device_id} (0x{device_id:x}), expected one of {self.device_ids}. Ignoring.")
            return

        logger.debug(f"rtl433: Received data {data}")
        self.signal.send(data)
