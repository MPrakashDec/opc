"""NSE/BSE expiry calendar.
Nifty 50 weekly expiry: Tuesday | Entry: Thursday 12:45 PM
Sensex weekly expiry: Thursday | Entry: Monday 12:45 PM
When expiry falls on holiday, it moves to previous trading day.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from holidays import adjust_expiry_for_holiday

# Weekday: Monday=0, Tuesday=1, Wednesday=2, Thursday=3, Friday=4
NIFTY_EXPIRY_WEEKDAY = 1   # Tuesday
SENSEX_EXPIRY_WEEKDAY = 3  # Thursday
NIFTY_ENTRY_WEEKDAY = 3    # Thursday
SENSEX_ENTRY_WEEKDAY = 0   # Monday


def _expiry_weekday(index: str) -> int:
    """Expiry weekday for index: 1=Tuesday (Nifty), 3=Thursday (Sensex)."""
    return NIFTY_EXPIRY_WEEKDAY if index.lower() == "nifty" else SENSEX_EXPIRY_WEEKDAY


def get_expiry_dates(from_date: date, to_date: date, index: str) -> list[date]:
    """Get all expiry dates for index between from_date and to_date.
    Nifty: Tuesday, Sensex: Thursday.
    Adjusted for holidays (moves to previous trading day).
    """
    wd = _expiry_weekday(index)
    expiries = []
    d = from_date
    while d <= to_date:
        days_until = (wd - d.weekday()) % 7
        next_exp = d + timedelta(days=days_until)
        if next_exp <= to_date:
            expiries.append(adjust_expiry_for_holiday(next_exp))
        d = next_exp + timedelta(days=1)
    return sorted(set(expiries))


def _entry_weekday(index: str) -> int:
    """Entry weekday: 3=Thursday (Nifty), 0=Monday (Sensex)."""
    return NIFTY_ENTRY_WEEKDAY if index.lower() == "nifty" else SENSEX_ENTRY_WEEKDAY


def get_entry_dates(from_date: date, to_date: date, index: str) -> list[date]:
    """Get entry dates for index. Nifty=Thursday, Sensex=Monday."""
    wd = _entry_weekday(index)
    dates = []
    d = from_date
    while d <= to_date:
        days_until = (wd - d.weekday()) % 7
        next_d = d + timedelta(days=days_until)
        if next_d <= to_date:
            dates.append(next_d)
        d = next_d + timedelta(days=1)
    return sorted(set(dates))


def _get_theoretical_expiries(entry_date: date, index: str) -> list[date]:
    """Get theoretical expiry dates (before holiday adjustment)."""
    wd = _expiry_weekday(index)
    expiries = []
    d = entry_date
    for _ in range(3):
        days_until = (wd - d.weekday()) % 7
        next_exp = d + timedelta(days=days_until)
        expiries.append(next_exp)
        d = next_exp + timedelta(days=1)
    return sorted(set(expiries))


def get_theoretical_expiry_for_entry(entry_date: date, expiry_code: int, index: str) -> date | None:
    """Get theoretical expiry (before holiday adjustment)."""
    theoretical = _get_theoretical_expiries(entry_date, index)
    if not theoretical:
        return None
    idx = min(expiry_code - 1, len(theoretical) - 1)
    return theoretical[idx]


def get_expiry_for_entry(entry_date: date, expiry_code: int, index: str) -> date | None:
    """Get adjusted expiry date (holiday moved to prev trading day).
    e.g. 2026-03-03 Holi -> 2026-03-02.
    """
    theoretical = _get_theoretical_expiries(entry_date, index)
    if not theoretical:
        return None
    idx = min(expiry_code - 1, len(theoretical) - 1)
    return adjust_expiry_for_holiday(theoretical[idx])


def get_exit_date_for_expiry(expiry_date: date, entry_date: date, theoretical_expiry: date | None = None) -> date:
    """Exit = 1 day before actual expiry (already holiday-adjusted) at 11:45 AM.
    When 2026-03-03 is holiday, expiry moves to 2026-03-02, so exit = 2026-02-27.
    If exit day is holiday, use previous trading day."""
    # Use adjusted expiry for exit calc (what API actually returns)
    ref = expiry_date
    if ref <= entry_date:
        return entry_date
    exit_candidate = ref - timedelta(days=1)
    return adjust_expiry_for_holiday(exit_candidate)


def get_entry_datetime(d: date) -> datetime:
    """Entry at 12:45 PM."""
    return datetime(d.year, d.month, d.day, 12, 45, 0)


def get_exit_datetime(d: date) -> datetime:
    """11:45 AM (1 day before expiry)."""
    return datetime(d.year, d.month, d.day, 11, 45, 0)
