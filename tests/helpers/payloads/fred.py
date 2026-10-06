"""FRED ``series/observations`` answers, written from the documented JSON format (no network).

Real-time period 1776-07-04..9999-12-31, output type 1: one row per observation and per span in
which its value stood, so a revised quarter appears once per value. ``"."`` is a missing value.
"""

import json
from typing import Any

SERIES_ID = "GDPC1"


def row(date: str, start: str, value: str, end: str = "9999-12-31") -> dict[str, str]:
    return {"realtime_start": start, "realtime_end": end, "date": date, "value": value}


# 2020-01-01 was revised twice (advance, second, third estimates); 2020-04-01 first stood in
# July, was revised in August; 2020-07-01 has a missing value in its first vintage.
OBSERVATIONS = [
    row("2020-01-01", "2020-04-29", "18951.9", "2020-05-27"),
    row("2020-01-01", "2020-05-28", "18924.3", "2020-06-24"),
    row("2020-01-01", "2020-06-25", "18560.0"),
    row("2020-04-01", "2020-07-30", "17302.5", "2020-08-26"),
    row("2020-04-01", "2020-08-27", "17258.2"),
    row("2020-07-01", "2020-10-29", "."),
]


def page(
    rows: list[dict[str, str]], count: int | None = None, offset: int = 0, limit: int = 100000
) -> bytes:
    """One answer page as FRED sends it (compact JSON)."""
    document: dict[str, Any] = {
        "realtime_start": "1776-07-04",
        "realtime_end": "9999-12-31",
        "observation_start": "1600-01-01",
        "observation_end": "9999-12-31",
        "units": "lin",
        "output_type": 1,
        "file_type": "json",
        "order_by": "observation_date",
        "sort_order": "asc",
        "count": len(rows) if count is None else count,
        "offset": offset,
        "limit": limit,
        "observations": rows,
    }
    return json.dumps(document, separators=(",", ":")).encode()


def payload() -> bytes:
    return page(OBSERVATIONS)


UNKNOWN_SERIES = b'{"error_code":400,"error_message":"Bad Request.  The series does not exist."}'
BAD_KEY = (
    b'{"error_code":400,"error_message":"Bad Request.  The value for variable api_key is not '
    b'registered.  Read https://fred.stlouisfed.org/docs/api/api_key.html"}'
)


def daily(*points: tuple[str, str, str]) -> bytes:
    """An unrevised daily series: ``(date, first known, value)`` per observation."""
    return page([row(d, start, value) for d, start, value in points])


# T10Y3M-like: a close published the next day, one holiday as ".".
CURVE = daily(
    ("2026-09-30", "2026-10-01", "0.10"),
    ("2026-10-01", "2026-10-02", "0.12"),
    ("2026-10-02", "2026-10-03", "."),
)
CURVE_REVISED = daily(
    ("2026-09-30", "2026-10-01", "0.10"),
    ("2026-10-01", "2026-10-02", "0.13"),  # the source corrected a number
    ("2026-10-02", "2026-10-03", "."),
)
