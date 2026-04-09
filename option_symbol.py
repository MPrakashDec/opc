"""Build index option trading symbols (NSE/BSE style) from expiry + strike."""
from __future__ import annotations

from datetime import date

_MONTHS = (
    "JAN", "FEB", "MAR", "APR", "MAY", "JUN",
    "JUL", "AUG", "SEP", "OCT", "NOV", "DEC",
)


def index_root_symbol(index: str) -> str:
    """Underlying root as used in contract names."""
    u = index.lower().strip()
    if u == "nifty":
        return "NIFTY"
    if u == "sensex":
        return "SENSEX"
    return index.upper().replace(" ", "")


def build_index_option_symbol(
    index: str,
    expiry: date,
    strike: float | int,
    option_type: str = "CE",
) -> str:
    """Trading symbol like NIFTY06FEB2524500CE or SENSEX10MAR2582100CE.

    Pattern: ROOT + DD + MMM + YY + STRIKE + CE|PE (common NSE index weekly style).
    """
    root = index_root_symbol(index)
    mon = _MONTHS[expiry.month - 1]
    yy = expiry.year % 100
    sk = int(round(float(strike)))
    ot = (option_type or "CE").upper()[:2]
    if ot not in ("CE", "PE"):
        ot = "CE"
    return f"{root}{expiry.day:02d}{mon}{yy}{sk}{ot}"


def strike_interval(index: str) -> int:
    """Strike spacing for ATM / ATM+2 / ATM+6 (100 for Nifty & Sensex index weekly)."""
    _ = index
    return 100


def strike_from_spot(spot: float, index: str) -> int:
    """Fallback ATM strike when API does not return strike series."""
    step = strike_interval(index)
    return int(round(float(spot) / step) * step)


def strike_from_atm_offset(atm_strike: int, offset_steps: int, index: str) -> int:
    """ATM+2 / ATM+6 style: offset_steps is +2 or +6 in strike intervals."""
    step = strike_interval(index)
    return int(atm_strike + offset_steps * step)


def normalize_strike_for_index(strike: float | int, index: str) -> int:
    """Round Nifty strikes to nearest 100; Sensex unchanged (integer rupees)."""
    x = float(strike)
    if index.lower() == "nifty":
        return int(round(x / 100) * 100)
    return int(round(x))
