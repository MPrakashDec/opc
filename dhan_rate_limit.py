"""Throttle calls to api.dhan.co to match DhanHQ published rate limits.

Official limits (Dhan support / docs, subject to change):
  - Data APIs: up to 10 requests per second
  - Non-Trading APIs: up to 20 requests per second
  - Quote APIs: 1 request per second (not used in this project)

We add a small cushion so bursts stay under the cap. Rolling / expired option
charts are treated as Data; margin calculator as Non-Trading.
"""
from __future__ import annotations

import threading
import time

# Minimum gap between calls (seconds). Slightly above 1/RPS to avoid edge bursts.
_DATA_INTERVAL = (1.0 / 10.0) + 0.02   # 10 rps → ~0.12s
_NT_INTERVAL = (1.0 / 20.0) + 0.01    # 20 rps → ~0.06s

_lock = threading.Lock()
_last_data_monotonic: float = 0.0
_last_nt_monotonic: float = 0.0


def _sleep_until_after(last_ts: float, interval: float) -> float:
    """Sleep if needed; return new last timestamp (monotonic)."""
    now = time.monotonic()
    wait = last_ts + interval - now
    if wait > 0:
        time.sleep(wait)
    return time.monotonic()


def throttle_dhan_data_api() -> None:
    """Call immediately before each Data API request (e.g. rolling options charts)."""
    global _last_data_monotonic
    with _lock:
        _last_data_monotonic = _sleep_until_after(_last_data_monotonic, _DATA_INTERVAL)


def throttle_dhan_non_trading_api() -> None:
    """Call immediately before each Non-Trading API request (e.g. margin calculator)."""
    global _last_nt_monotonic
    with _lock:
        _last_nt_monotonic = _sleep_until_after(_last_nt_monotonic, _NT_INTERVAL)
