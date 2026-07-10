import threading


class ResettableTimer:
    def __init__(self, interval, function, args=None):
        self.interval = interval
        self.function = function
        self.args = args if args is not None else tuple()
        self.timer = None

    def _start_timer(self):
        self.timer = threading.Timer(self.interval, self.function, self.args)
        self.timer.start()

    def start(self):
        if self.timer is not None:
            self.timer.cancel()
            self.timer = None
        self._start_timer()
