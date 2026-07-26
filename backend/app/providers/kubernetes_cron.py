"""Small, dependency-free CronJob schedule parser.

Kubernetes CronJobs use the standard five-field cron format plus a limited set
of macros.  The collector only needs the most recent expected schedule, so this
module deliberately does not implement command execution or mutation.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


_CRON_MACROS = {
    "@yearly": "0 0 1 1 *",
    "@annually": "0 0 1 1 *",
    "@monthly": "0 0 1 * *",
    "@weekly": "0 0 * * 0",
    "@daily": "0 0 * * *",
    "@midnight": "0 0 * * *",
    "@hourly": "0 * * * *",
}
_MONTH_NAMES = {
    name: str(index)
    for index, name in enumerate(
        (
            "JAN",
            "FEB",
            "MAR",
            "APR",
            "MAY",
            "JUN",
            "JUL",
            "AUG",
            "SEP",
            "OCT",
            "NOV",
            "DEC",
        ),
        start=1,
    )
}
_WEEKDAY_NAMES = {
    name: str(index)
    for index, name in enumerate(
        ("SUN", "MON", "TUE", "WED", "THU", "FRI", "SAT")
    )
}


def _cron_values(
    expression: str,
    minimum: int,
    maximum: int,
    names: dict[str, str] | None = None,
) -> set[int]:
    normalized = expression.upper()
    for name, value in (names or {}).items():
        normalized = re.sub(rf"\b{name}\b", value, normalized)
    if normalized == "?":
        normalized = "*"
    values: set[int] = set()
    for part in normalized.split(","):
        item, separator, step_text = part.partition("/")
        step = int(step_text) if separator else 1
        if step <= 0:
            raise ValueError("cron step must be positive")
        if item == "*":
            start, end = minimum, maximum
        elif "-" in item:
            start_text, end_text = item.split("-", 1)
            start, end = int(start_text), int(end_text)
        else:
            start = int(item)
            end = maximum if separator else start
        if start < minimum or end > maximum or start > end:
            raise ValueError("cron field is outside its valid range")
        values.update(range(start, end + 1, step))
    return values


def _cron_day_matches(
    value: datetime,
    days_of_month: set[int],
    weekdays: set[int],
    dom_wildcard: bool,
    dow_wildcard: bool,
) -> bool:
    # Cron uses Sunday=0/7; Python uses Monday=0.
    cron_weekday = (value.weekday() + 1) % 7
    dom_match = value.day in days_of_month
    dow_match = cron_weekday in weekdays or (
        cron_weekday == 0 and 7 in weekdays
    )
    if dom_wildcard and dow_wildcard:
        return True
    if dom_wildcard:
        return dow_match
    if dow_wildcard:
        return dom_match
    return dom_match or dow_match


def latest_cron_schedule(
    schedule: str,
    timezone_name: str | None,
    now: datetime,
) -> datetime | None:
    """Return the latest schedule older than the two-minute observation grace."""

    fields = _CRON_MACROS.get(schedule.casefold(), schedule).split()
    if len(fields) != 5:
        raise ValueError(
            "CronJob schedule must contain five fields or a supported macro"
        )
    try:
        minutes = _cron_values(fields[0], 0, 59)
        hours = _cron_values(fields[1], 0, 23)
        days = _cron_values(fields[2], 1, 31)
        months = _cron_values(fields[3], 1, 12, _MONTH_NAMES)
        weekdays = _cron_values(fields[4], 0, 7, _WEEKDAY_NAMES)
        zone = ZoneInfo(timezone_name or "UTC")
    except ZoneInfoNotFoundError as exc:
        raise ValueError("CronJob timeZone is invalid") from exc
    local_now = now.astimezone(zone).replace(second=0, microsecond=0)
    cutoff = local_now - timedelta(minutes=2)
    for day_offset in range(367):
        day = cutoff - timedelta(days=day_offset)
        if day.month not in months or not _cron_day_matches(
            day,
            days,
            weekdays,
            fields[2] in {"*", "?"},
            fields[4] in {"*", "?"},
        ):
            continue
        candidates = [
            day.replace(hour=hour, minute=minute)
            for hour in hours
            for minute in minutes
            if day.replace(hour=hour, minute=minute) <= cutoff
        ]
        if candidates:
            return max(candidates).astimezone(timezone.utc)
    return None
