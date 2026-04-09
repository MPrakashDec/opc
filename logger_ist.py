"""Logging with Indian Standard Time (IST) timestamps."""
from __future__ import annotations

from datetime import datetime

import pytz

IST = pytz.timezone("Asia/Kolkata")


def log(msg: str, level: str = "INFO") -> None:
    """Minimal logging (ASCII-safe for Windows consoles). DEBUG is silent."""
    if level == "DEBUG":
        return
    if level == "INFO":
        print(msg, flush=True)
    elif level == "WARN":
        print(f"[WARN] {msg}", flush=True)
    elif level == "ERROR":
        print(f"[ERROR] {msg}", flush=True)


def progress(msg: str) -> None:
    """Timestamped step (IST); use during long runs so the console shows what is running."""
    t = datetime.now(IST).strftime("%H:%M:%S")
    print(f"[{t} IST] >> {msg}", flush=True)


def ts_to_ist(dt: datetime) -> str:
    """Convert datetime to IST string. Naive dt assumed as IST (market hours)."""
    if dt.tzinfo is None:
        dt = IST.localize(dt)
    elif dt.tzinfo != IST:
        dt = dt.astimezone(IST)
    return dt.strftime("%Y-%m-%d %H:%M:%S IST")


def ts_to_iso_ist(dt: datetime) -> str:
    """Convert datetime to ISO format with +05:30 (for CSV)."""
    if dt.tzinfo is None:
        dt = IST.localize(dt)
    elif dt.tzinfo != IST:
        dt = dt.astimezone(IST)
    return dt.strftime("%Y-%m-%dT%H:%M:%S+05:30")


def ts_to_csv_display_ist(dt: datetime) -> str:
    """Readable IST for CSV/screen: 2026-02-12 12:45"""
    if dt.tzinfo is None:
        dt = IST.localize(dt)
    elif dt.tzinfo != IST:
        dt = dt.astimezone(IST)
    return dt.strftime("%Y-%m-%d %H:%M")
