import time
import random

class SafetyManager:
    def __init__(self):
        self.last_requests = {}

    def _wait_for_rate_limit(self, key, min_interval):
        now = time.time()
        elapsed = now - self.last_requests.get(key, 0)
        if elapsed < min_interval:
            time.sleep(min_interval - elapsed)
        self.last_requests[key] = time.time()

    def request_dhan_quote(self):
        self._wait_for_rate_limit("dhan_quote", 1.1)

    def human_delay(self, min_s=0.5, max_s=2.0):
        time.sleep(random.uniform(min_s, max_s))
