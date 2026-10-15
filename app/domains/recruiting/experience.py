"""Deterministic experience math. The LLM extracts dates; code does the arithmetic.

Models don't always follow the requested YYYY-MM format, so parsing is deliberately
lenient: "2021-03", "2021-03-01", "2021", "03/2021", "Mar 2021", "March 2021" and
"Sept. 2021" all work.
"""

import re
from collections.abc import Iterable
from datetime import date

from app.domains.recruiting.schemas import WorkExperience

_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1
)}
_CURRENT_MARKERS = {"present", "current", "now", "today", "ongoing"}


def parse_month(value: str | None) -> int | None:
    """A date string -> absolute month index; None if missing or unrecognized."""
    if not value:
        return None
    v = value.strip().lower().replace(".", "")
    if m := re.fullmatch(r"(\d{4})(?:[-/](\d{1,2})(?:[-/]\d{1,2})?)?", v):  # 2021-03(-15), 2021
        year, month = int(m[1]), int(m[2] or 1)
    elif m := re.fullmatch(r"(\d{1,2})[-/](\d{4})", v):  # 03/2021
        month, year = int(m[1]), int(m[2])
    elif m := re.fullmatch(r"([a-z]+),?\s+(\d{4})", v):  # mar 2021, march 2021, sept 2021
        month, year = _MONTHS.get(m[1][:3]), int(m[2])
        if month is None:
            return None
    else:
        return None
    if not 1 <= month <= 12:
        return None
    return year * 12 + month - 1


def is_current_marker(value: str | None) -> bool:
    return bool(value) and value.strip().lower() in _CURRENT_MARKERS


def total_years_experience(roles: Iterable[WorkExperience], as_of: date) -> float:
    """Years covered by at least one role (months inclusive, overlaps counted once)."""
    now = as_of.year * 12 + as_of.month - 1
    months: set[int] = set()
    for role in roles:
        start = parse_month(role.start_date)
        # A real end date beats the is_current flag: models sometimes set both.
        end = parse_month(role.end_date)
        if end is None and (role.is_current or is_current_marker(role.end_date)):
            end = now
        if start is None or end is None:
            continue  # can't place this role in time; don't guess
        months.update(range(start, min(end, now) + 1))
    return round(len(months) / 12, 2)
