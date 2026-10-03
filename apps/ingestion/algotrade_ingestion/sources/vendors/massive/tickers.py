"""Massive ticker list: every active US stock/ETF with FIGI, CIK and type (``MassiveTickers``)."""

import json
from typing import Any

import pandas as pd

from algotrade_ingestion.sources.framework.base import FetchRequest, Normalized
from algotrade_ingestion.sources.vendors.massive.client import HOST, _Massive, act_symbol

TICKERS = HOST + "/v3/reference/tickers?market=stocks&active=true&limit=1000"


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


class MassiveTickers(_Massive):
    """Every active US stock/ETF ticker with FIGI, CIK and type. Request key: ``active``."""

    dataset = "tickers"

    def fetch(self, request: FetchRequest) -> bytes | None:
        return self._paged(TICKERS)

    def normalize(self, request: FetchRequest, payload: bytes) -> Normalized | None:
        frame = parse_tickers(json.loads(payload).get("results") or [])
        return (
            None
            if frame.empty
            else Normalized(session_date=None, tables={}, parsed={"tickers": frame})
        )
