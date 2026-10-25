"""Massive ticker list: every US stock/ETF with FIGI, CIK and type (``MassiveTickers``).

Request key ``active`` (the default) lists the live names (identifiers for the universe build);
request key ``inactive`` lists the delisted ones (ADR 0084, ``instruments/delisted_tickers``):
``active=false``, ``type`` is null before 2017, FIGI / CIK are partial, no OTC names, ETFs only
from 2016 and a renamed company's old ticker is absent (measured 2026-10-24: 23,557 records, 24
pages of 1000). Both page through ``next_url`` with the key in the Authorization header only,
each page one request of the shared ``massive`` limiter (free tier 5 a minute, 12.5 s apart, so
the inactive list takes about five minutes). A ticker goes through ``act_symbol`` for both, the
same symbol space as the universe and ``symbol_history`` (``KIMpL`` -> ``KIM$L``); no two
delisted records collapsed on it at the first pull. ``delisted_utc`` is Massive's last trading
day at midnight New York time; its date part is the ``end_date`` (null where Massive has none).
"""

import json
from datetime import date
from typing import Any

import pandas as pd

from algotrade_sources.framework.base import FetchRequest, Normalized
from algotrade_sources.vendors.massive.client import HOST, _Massive, act_symbol

TICKERS = HOST + "/v3/reference/tickers?market=stocks&active=true&limit=1000"
INACTIVE_TICKERS = HOST + "/v3/reference/tickers?market=stocks&active=false&limit=1000"
INACTIVE = "inactive"  # the request key of the delisted list
DELISTED_TABLE = "instruments/delisted_tickers"  # the key of its ``Normalized.parsed`` frame
DELISTED_COLUMNS = [
    "ticker",
    "name",
    "exchange",
    "vendor_type",
    "security_type",
    "cik",
    "figi",
    "share_class_figi",
    "end_date",
]


# Massive security types -> ours. Unknown codes stay None (our name rules decide).
MASSIVE_TYPES = {
    "CS": "COMMON_STOCK",
    "OS": "COMMON_STOCK",
    "ADRC": "ADR",
    "ADRP": "PREFERRED",
    "ADRW": "WARRANT",
    "ADRR": "RIGHT",
    "GDR": "ADR",
    "ETF": "ETF",
    "ETN": "ETN",
    "ETV": "ETF",
    "ETS": "ETF",
    "PFD": "PREFERRED",
    "WARRANT": "WARRANT",
    "RIGHT": "RIGHT",
    "UNIT": "UNIT",
    "SP": "NOTE",
    "BOND": "NOTE",
    "BASKET": "ETF",
    "FUND": "CEF",
    "LT": "COMMON_STOCK",
}


def parse_tickers(results: list[dict[str, Any]]) -> pd.DataFrame:
    """Massive ticker list -> identifiers and vendor type per ACT symbol."""
    rows = [
        {
            "symbol": act_symbol(str(r["ticker"])),
            "figi": r.get("composite_figi") or None,
            "share_class_figi": r.get("share_class_figi") or None,
            "cik": r.get("cik") or None,
            "vendor_type": r.get("type") or None,
            "vendor_security_type": MASSIVE_TYPES.get(str(r.get("type"))),
        }
        for r in results
        if r.get("ticker")
    ]
    columns = ["symbol", "figi", "share_class_figi", "cik", "vendor_type", "vendor_security_type"]
    return pd.DataFrame(rows, columns=columns).drop_duplicates("symbol", keep="first")


def _day(value: object) -> date | None:
    """The date part of Massive's ``delisted_utc`` (``2008-02-11T05:00:00Z``), else ``None``."""
    try:
        return date.fromisoformat(str(value)[:10]) if value else None
    except ValueError:
        return None


def parse_inactive(results: list[dict[str, Any]]) -> tuple[pd.DataFrame, dict[str, int]]:
    """Massive's inactive ticker list -> (``DELISTED_COLUMNS`` rows, notes). A repeat of a
    (ticker, ``end_date``) pair is dropped and counted (``dropped_duplicate``)."""
    rows = [
        {
            "ticker": act_symbol(str(r["ticker"])),
            "name": r.get("name") or None,
            "exchange": r.get("primary_exchange") or None,
            "vendor_type": r.get("type") or None,
            "security_type": MASSIVE_TYPES.get(str(r.get("type"))),
            "cik": r.get("cik") or None,
            "figi": r.get("composite_figi") or None,
            "share_class_figi": r.get("share_class_figi") or None,
            "end_date": _day(r.get("delisted_utc")),
        }
        for r in results
        if r.get("ticker")
    ]
    frame = pd.DataFrame(rows, columns=DELISTED_COLUMNS)
    kept = frame.drop_duplicates(["ticker", "end_date"], keep="first").reset_index(drop=True)
    return kept, {"dropped_duplicate": len(frame) - len(kept)}


class MassiveTickers(_Massive):
    """Every US stock/ETF ticker with FIGI, CIK and type. Request keys: ``active`` (live names,
    the default) and ``inactive`` (delisted names with their last trading day)."""

    dataset = "tickers"

    def fetch(self, request: FetchRequest) -> bytes | None:
        return self._paged(INACTIVE_TICKERS if request.key == INACTIVE else TICKERS)

    def normalize(self, request: FetchRequest, payload: bytes) -> Normalized | None:
        results = json.loads(payload).get("results") or []
        if request.key == INACTIVE:
            delisted, notes = parse_inactive(results)
            return (
                None
                if delisted.empty
                else Normalized(None, {}, notes, parsed={DELISTED_TABLE: delisted})
            )
        frame = parse_tickers(results)
        return (
            None
            if frame.empty
            else Normalized(session_date=None, tables={}, parsed={"tickers": frame})
        )
