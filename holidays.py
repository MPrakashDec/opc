"""NSE/BSE trading holidays. When expiry falls on a holiday, it moves to previous trading day."""
from __future__ import annotations

from datetime import date, timedelta

# NSE/BSE trading holidays (YYYY, MM, DD)
# Source: NSE/BSE holiday circulars
HOLIDAYS: set[date] = {
    # 2024
    date(2024, 1, 26),   # Republic Day
    date(2024, 3, 8),    # Mahashivratri
    date(2024, 3, 25),   # Holi
    date(2024, 3, 29),   # Good Friday
    date(2024, 4, 11),   # Id-ul-Fitr
    date(2024, 4, 17),   # Ram Navami
    date(2024, 4, 21),   # Mahavir Jayanti
    date(2024, 5, 1),    # Maharashtra Day
    date(2024, 5, 23),   # Buddha Purnima
    date(2024, 6, 17),   # Bakri Id
    date(2024, 7, 17),   # Muharram
    date(2024, 8, 15),   # Independence Day
    date(2024, 8, 26),   # Janmashtami
    date(2024, 9, 16),   # Milad-un-Nabi
    date(2024, 10, 2),   # Mahatma Gandhi Jayanti
    date(2024, 10, 12),  # Dussehra
    date(2024, 10, 31),  # Diwali
    date(2024, 11, 1),   # Diwali Balipratipada
    date(2024, 11, 15),  # Guru Nanak Jayanti
    date(2024, 12, 25),  # Christmas
    # 2025
    date(2025, 1, 26),   # Republic Day
    date(2025, 3, 14),   # Mahashivratri
    date(2025, 3, 25),   # Holi
    date(2025, 4, 18),   # Good Friday
    date(2025, 4, 21),   # Ram Navami
    date(2025, 5, 1),    # Maharashtra Day
    date(2025, 6, 6),    # Bakri Id
    date(2025, 7, 7),    # Muharram
    date(2025, 8, 15),   # Independence Day
    date(2025, 8, 16),   # Parsi New Year
    date(2025, 10, 2),   # Mahatma Gandhi Jayanti
    date(2025, 10, 2),   # Mahalaya Amavasya
    date(2025, 10, 20),  # Dussehra
    date(2025, 10, 20),  # Diwali
    date(2025, 10, 21),  # Diwali Balipratipada
    date(2025, 11, 5),   # Guru Nanak Jayanti
    date(2025, 12, 25),  # Christmas
    # 2026
    date(2026, 1, 26),   # Republic Day
    date(2026, 3, 3),    # Holi
    date(2026, 3, 26),   # Ram Navami
    date(2026, 3, 31),   # Mahavir Jayanti
    date(2026, 4, 3),    # Good Friday
    date(2026, 4, 14),   # Ambedkar Jayanti
    date(2026, 5, 1),    # Maharashtra Day
    date(2026, 5, 28),   # Bakri Id
    date(2026, 6, 26),   # Muharram
    date(2026, 9, 14),   # Ganesh Chaturthi
    date(2026, 10, 2),   # Gandhi Jayanti
    date(2026, 10, 20),  # Dussehra
    date(2026, 11, 8),   # Diwali
    date(2026, 11, 9),   # Diwali Balipratipada
    date(2026, 11, 24),  # Guru Nanak Jayanti
    date(2026, 12, 25),  # Christmas
}


def is_holiday(d: date) -> bool:
    """Check if date is NSE/BSE trading holiday (or weekend)."""
    if d.weekday() >= 5:  # Saturday=5, Sunday=6
        return True
    return d in HOLIDAYS


def adjust_expiry_for_holiday(expiry_date: date) -> date:
    """If expiry falls on holiday/weekend, return previous trading day."""
    d = expiry_date
    while is_holiday(d):
        d = d - timedelta(days=1)
    return d
