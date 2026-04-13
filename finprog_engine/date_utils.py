from __future__ import annotations

from datetime import date, timedelta
from calendar import monthrange


def parse_iso_date(value: str | None) -> date | None:
    if not value:
        return None
    year, month, day = map(int, value.split("-"))
    return date(year, month, day)


def to_iso_date(value: date) -> str:
    return value.isoformat()


def add_days(value: date, days: int) -> date:
    return value + timedelta(days=days)


def clamp_day(year: int, month: int, desired_day: int) -> int:
    return min(desired_day, monthrange(year, month)[1])


def build_date(year: int, month: int, day: int) -> date:
    return date(year, month, clamp_day(year, month, day))


def add_months_clamped(value: date, month_count: int) -> date:
    month_index = value.month - 1 + month_count
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    return build_date(year, month, value.day)


def add_years_clamped(value: date, year_count: int) -> date:
    return build_date(value.year + year_count, value.month, value.day)


def is_within_range(value: date, start: date, end: date) -> bool:
    return start <= value <= end

