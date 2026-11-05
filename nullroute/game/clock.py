"""Game time. One real second equals one game minute."""

from __future__ import annotations

from datetime import datetime, timedelta

EPOCH = datetime(2031, 3, 14, 8, 0, 0)
GAME_MINUTES_PER_REAL_SECOND = 1.0


def to_dt(minutes: float) -> datetime:
    return EPOCH + timedelta(minutes=minutes)


def fmt_log(minutes: float) -> str:
    """Syslog style timestamp: 'Mar 14 08:01:22'."""
    return to_dt(minutes).strftime("%b %d %H:%M:%S")


def fmt_status(minutes: float) -> str:
    return to_dt(minutes).strftime("%a %d %b %H:%M")


def fmt_date(minutes: float) -> str:
    return to_dt(minutes).strftime("%a %b %d %H:%M:%S UTC %Y")


def fmt_short(minutes: float) -> str:
    return to_dt(minutes).strftime("%b %d %H:%M")


def fmt_duration(minutes: float) -> str:
    minutes = max(0, int(minutes))
    days, rem = divmod(minutes, 1440)
    hours, mins = divmod(rem, 60)
    if days:
        return f"{days}d {hours}h"
    if hours:
        return f"{hours}h {mins:02d}m"
    return f"{mins}m"


def parse_duration(text: str) -> float | None:
    """Parse '30', '30s', '15m', '2h', '1d' into game minutes.

    A bare number or 's' suffix means real seconds, which equal game minutes.
    """
    text = text.strip().lower()
    if not text:
        return None
    unit = text[-1]
    num = text[:-1] if unit.isalpha() else text
    try:
        value = float(num)
    except ValueError:
        return None
    if not unit.isalpha() or unit == "s":
        return value * GAME_MINUTES_PER_REAL_SECOND
    if unit == "m":
        return value
    if unit == "h":
        return value * 60
    if unit == "d":
        return value * 1440
    return None
