"""Small formatting + date helpers used across templates."""

from __future__ import annotations

import calendar
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")

_MONTHS = [
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
]


def month_bounds(year: int, month: int) -> tuple[date, date]:
    """First and last date of the given month."""
    first = date(year, month, 1)
    _, last_day = calendar.monthrange(year, month)
    return first, date(year, month, last_day)


def month_grid(year: int, month: int) -> list[list[date | None]]:
    """6×7 grid for the month. Each cell is a date or None (outside month).
    Week starts Monday (Indian convention is mixed; Mon-start reads better for weekly expiries).
    """
    cal = calendar.Calendar(firstweekday=0)  # Monday
    weeks = []
    for week in cal.monthdayscalendar(year, month):
        weeks.append([date(year, month, d) if d else None for d in week])
    return weeks


def prev_month(year: int, month: int) -> tuple[int, int]:
    return (year - 1, 12) if month == 1 else (year, month - 1)


def next_month(year: int, month: int) -> tuple[int, int]:
    return (year + 1, 1) if month == 12 else (year, month + 1)


def month_name(month: int) -> str:
    return _MONTHS[month - 1]


def today_ist() -> date:
    return datetime.now(IST).date()


def ist_from_utc_iso(ts: str | None) -> datetime | None:
    """Parse a UTC ISO string from the DB and return an IST-aware datetime."""
    if not ts:
        return None
    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    return dt.astimezone(IST)


def fmt_time_ist(ts: str | None) -> str:
    dt = ist_from_utc_iso(ts)
    return dt.strftime("%H:%M") if dt else "—"


def fmt_date_iso(d: date) -> str:
    return d.isoformat()


def shift_day(d: date, delta: int) -> date:
    return d + timedelta(days=delta)


# Retained for compatibility — the web UI now derives expiry days from the
# user's own trade history (see queries.expiry_days_in_range). This helper
# defaults to False so templates without an `expiry_days` set don't light up
# days that aren't actually expiries.
def is_expiry_day(d: date, expiry_days: frozenset[date] | None = None) -> bool:
    if expiry_days is None:
        return False
    return d in expiry_days
