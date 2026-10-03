"""Massive splits and dividends (``MassiveCorporateActions``).

Splits ``/stocks/v1/splits``, dividends ``/stocks/v1/dividends``: filtered by date, paginated
through ``next_url``.
"""

import json
from datetime import date
from typing import Any

import pandas as pd

from algotrade_sources.framework.base import FetchRequest, Normalized
from algotrade_sources.vendors.massive.client import HOST, _Massive, _ts, act_symbol

SPLITS = HOST + "/stocks/v1/splits?execution_date.gte={start}&execution_date.lte={end}&limit=5000"
DIVIDENDS = (
    HOST + "/stocks/v1/dividends?ex_dividend_date.gte={start}&ex_dividend_date.lte={end}&limit=5000"
)


def parse_splits(results: list[dict[str, Any]]) -> pd.DataFrame:
    rows = [
        {
            "ts": _ts(r["execution_date"]),
            "symbol": act_symbol(str(r["ticker"])),
            "split_from": float(r["split_from"]),
            "split_to": float(r["split_to"]),
            "ratio": float(r["split_to"]) / float(r["split_from"]),
            "adjustment_type": r.get("adjustment_type"),
        }
        for r in results
        if r.get("ticker") and r.get("split_from") and r.get("split_to")
    ]
    return pd.DataFrame(
        rows,
        columns=["ts", "symbol", "split_from", "split_to", "ratio", "adjustment_type"],
    ).drop_duplicates(["symbol", "ts"])


def parse_dividends(results: list[dict[str, Any]]) -> pd.DataFrame:
    rows = [
        {
            "ts": _ts(r["ex_dividend_date"]),
            "symbol": act_symbol(str(r["ticker"])),
            "cash_amount": float(r["cash_amount"]),
            "currency": r.get("currency"),
            "pay_date": r.get("pay_date"),
            "record_date": r.get("record_date"),
            "declaration_date": r.get("declaration_date"),
            "frequency": r.get("frequency"),
            "distribution_type": r.get("distribution_type"),
        }
        for r in results
        if r.get("ticker") and r.get("ex_dividend_date") and r.get("cash_amount")
    ]
    columns = [
        "symbol",
        "ts",
        "cash_amount",
        "currency",
        "pay_date",
        "record_date",
        "declaration_date",
        "frequency",
        "distribution_type",
    ]
    # Several distributions can share an ex-date (special + regular): keep them all, summed.
    frame = pd.DataFrame(rows, columns=columns)
    if frame.empty:
        return frame
    return (
        frame.groupby(["symbol", "ts"], as_index=False).agg(
            {**dict.fromkeys(columns[2:], "first"), "cash_amount": "sum"}
        )
    )[columns]


class MassiveCorporateActions(_Massive):
    """Request key: ``splits:<start>:<end>`` or ``dividends:<start>:<end>`` (ISO dates)."""

    dataset = "corporate_actions"

    def window_requests(
        self, start: date, end: date, session: date
    ) -> list[tuple[str, FetchRequest]]:
        """(label, request) per kind for events in ``[start, end]`` (``WindowedSource``)."""
        span = f"{start.isoformat()}:{end.isoformat()}"
        return [
            (kind, FetchRequest(f"{kind}:{span}", session_date=session))
            for kind in ("splits", "dividends")
        ]

    def fetch(self, request: FetchRequest) -> bytes | None:
        kind, start, end = request.key.split(":")
        template = {"splits": SPLITS, "dividends": DIVIDENDS}[kind]
        return self._paged(template.format(start=start, end=end))

    def normalize(self, request: FetchRequest, payload: bytes) -> Normalized | None:
        kind = request.key.split(":")[0]
        results = json.loads(payload).get("results") or []
        table, frame = (
            ("events/split", parse_splits(results))
            if kind == "splits"
            else ("events/dividend", parse_dividends(results))
        )
        return Normalized(session_date=None, tables={table: frame})
