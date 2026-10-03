"""Nasdaq public earnings calendar: every US company reporting on a date.

``https://api.nasdaq.com/api/calendar/earnings?date=YYYY-MM-DD`` (unofficial, free, no key;
see docs/data/vendors.md). Future dates carry the EPS forecast and number of estimates; past
dates also carry the reported EPS and the surprise. Weekends and holidays return no rows,
which is a valid answer, not an error. Rows carry ``symbol``; the job resolves
``instrument_id`` through the reference (ADR 0018).
"""

import json
import math
from datetime import date
from typing import Any

import pandas as pd

from algotrade_sources.framework.base import FetchRequest, Normalized
from algotrade_sources.framework.http import Http

SOURCE = "nasdaq_earnings"
DATASET = "earnings_calendar"
TABLE = "events/earnings"
URL = "https://api.nasdaq.com/api/calendar/earnings?date={date}"
TIMES = {
    "time-pre-market": "pre_market",
    "time-after-hours": "after_hours",
    "time-not-supplied": "unknown",
}
COLUMNS = (
    "symbol",
    "ts",
    "earnings_date",
    "time",
    "fiscal_quarter",
    "eps_forecast",
    "estimates",
    "eps_reported",
    "surprise_pct",
    "reported",
)


def _money(value: Any) -> float | None:
    text = (
        str(value or "")
        .replace("$", "")
        .replace(",", "")
        .replace("(", "-")
        .replace(")", "")
        .strip()
    )
    try:
        number = float(text)
    except ValueError:
        return None
    return None if math.isnan(number) else number


def parse_calendar(day: date, payload: bytes) -> pd.DataFrame:
    """One row per company reporting on ``day`` (``COLUMNS``); empty for no reports."""
    doc = json.loads(payload)
    rows = ((doc.get("data") or {}).get("rows")) or []
    records = []
    for r in rows:
        symbol = str(r.get("symbol") or "").strip().upper()
        if not symbol:
            continue
        reported = _money(r.get("eps"))
        records.append(
            {
                "symbol": symbol,
                "ts": pd.Timestamp(day, tz="UTC"),
                "earnings_date": day,
                "time": TIMES.get(str(r.get("time")), "unknown"),
                "fiscal_quarter": r.get("fiscalQuarterEnding") or None,
                "eps_forecast": _money(r.get("epsForecast")),
                "estimates": _money(r.get("noOfEsts")),
                "eps_reported": reported,
                "surprise_pct": _money(r.get("surprise")),
                "reported": reported is not None,
            }
        )
    return pd.DataFrame(records, columns=list(COLUMNS))


class NasdaqEarningsSource:
    """Implements ``sources.base.Source``. Request key: an ISO date."""

    name = SOURCE
    dataset = DATASET

    def __init__(self, http: Http) -> None:
        self._http = http  # paced by the shared ``nasdaq`` limiter (sources.toml)

    def fetch(self, request: FetchRequest) -> bytes | None:
        return self._http.get(URL.format(date=date.fromisoformat(request.key).isoformat()))

    def normalize(self, request: FetchRequest, payload: bytes) -> Normalized | None:
        day = date.fromisoformat(request.key)
        return Normalized(session_date=day, tables={TABLE: parse_calendar(day, payload)})
