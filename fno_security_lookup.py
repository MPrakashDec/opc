"""Resolve Dhan SECURITY_ID for index options from the official detailed scrip CSV."""
from __future__ import annotations

import time
from datetime import date
from pathlib import Path

import pandas as pd
import requests

DETAILED_CSV_URL = "https://images.dhan.co/api-data/api-scrip-master-detailed.csv"
CACHE_DIR = Path(__file__).resolve().parent / ".cache"
CACHE_FILE = CACHE_DIR / "api-scrip-master-detailed.csv"
CACHE_MAX_AGE_SEC = 24 * 3600

_df_cache: pd.DataFrame | None = None


def _underlying_symbol(index: str) -> str:
    u = index.lower().strip()
    if u == "nifty":
        return "NIFTY"
    if u == "sensex":
        return "SENSEX"
    return index.upper().replace(" ", "")


def _exchange_segment(index: str) -> str:
    return "NSE_FNO" if index.lower().strip() == "nifty" else "BSE_FNO"


def get_scrip_master_detailed_df(force_refresh: bool = False) -> pd.DataFrame:
    """Load Dhan detailed instrument CSV (cached on disk, refreshed after 24h)."""
    global _df_cache
    if _df_cache is not None and not force_refresh:
        return _df_cache

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    need_download = force_refresh or not CACHE_FILE.exists()
    if CACHE_FILE.exists() and not need_download:
        age = time.time() - CACHE_FILE.stat().st_mtime
        if age > CACHE_MAX_AGE_SEC:
            need_download = True
    if need_download:
        r = requests.get(DETAILED_CSV_URL, timeout=120)
        r.raise_for_status()
        CACHE_FILE.write_bytes(r.content)

    _df_cache = pd.read_csv(CACHE_FILE, low_memory=False)
    return _df_cache


def find_option_security_id(
    df: pd.DataFrame,
    index: str,
    expiry: date,
    strike: int,
    option_type: str = "CE",
) -> str | None:
    """Return SECURITY_ID string for OPTIDX option, or None if not found."""
    und = _underlying_symbol(index)
    ot = (option_type or "CE").upper()
    seg = _exchange_segment(index)
    exch = "NSE" if seg == "NSE_FNO" else "BSE"

    m = (
        (df["INSTRUMENT"] == "OPTIDX")
        & (df["UNDERLYING_SYMBOL"] == und)
        & (df["OPTION_TYPE"] == ot)
        & (df["EXCH_ID"] == exch)
    )
    sub = df.loc[m].copy()
    if sub.empty:
        return None

    sub["_exp"] = pd.to_datetime(sub["SM_EXPIRY_DATE"], errors="coerce").dt.date
    sub = sub[sub["_exp"] == expiry]
    if sub.empty:
        return None

    sk = int(round(float(strike)))
    sub["_sk"] = pd.to_numeric(sub["STRIKE_PRICE"], errors="coerce").fillna(-1).round(0).astype(int)
    sub = sub[sub["_sk"] == sk]
    if sub.empty:
        return None

    return str(int(sub.iloc[0]["SECURITY_ID"]))


def exchange_segment_for_index(index: str) -> str:
    return _exchange_segment(index)
