from __future__ import annotations

import calendar
from datetime import date, datetime, timedelta
from typing import Any

WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def month_grid(year: int, month: int) -> list[list[date]]:
    """Return a stable 6x7 Monday-first grid, including adjacent-month dates."""
    weeks = [
        list(week)
        for week in calendar.Calendar(firstweekday=calendar.MONDAY).monthdatescalendar(
            year, month
        )
    ]
    while len(weeks) < 6:
        last = weeks[-1][-1] + timedelta(days=1)
        weeks.append([last + timedelta(days=offset) for offset in range(7)])
    return weeks[:6]


def parse_date(text: str) -> date | None:
    """Accept dd-mm-yyyy (primary), dd/mm/yyyy and yyyy-mm-dd."""
    value = (text or "").strip()
    if not value:
        return None
    for fmt in ("%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def format_short(value: date) -> str:
    return value.strftime("%d-%m-%Y")


def shift_month(year: int, month: int, delta: int) -> tuple[int, int]:
    index = year * 12 + (month - 1) + delta
    return index // 12, index % 12 + 1


def date_key(value: date) -> str:
    return value.isoformat()


def from_key(value: str) -> date | None:
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def selection_data(year: int, month: int, selected: date) -> dict[str, Any]:
    return {"year": year, "month": month, "selected": date_key(selected)}
