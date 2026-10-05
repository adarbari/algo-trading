"""Massive ticker overview: a company's description, website and head count (``MassiveOverview``).

``GET /v3/reference/tickers/{ticker}`` is one request per ticker. Checked 2026-10-04 on the
free tier: stocks and ADRs (AAPL, KO, PLTR, TSM) return ``description`` (a paragraph of plain
text), ``homepage_url`` and ``total_employees``; ETFs (SPY, QQQ, XLK, ARKK, JEPI, BITO) answer
200 with identity fields only, no description. A ticker Massive does not know answers 404
(``None`` from the HTTP client). ETFs are described from SEC prospectuses instead
(``vendors/sec/fund_objectives.py``).

Rows carry the vendor ``symbol`` (ACT style); the task resolves ``instrument_id`` (ADR 0018).
"""

import json
import re
from urllib.parse import quote

import pandas as pd

from algotrade_sources.framework.base import FetchRequest, Normalized
from algotrade_sources.vendors.massive.client import HOST, _Massive, act_symbol

OVERVIEW = HOST + "/v3/reference/tickers/{ticker}"
COLUMNS = ["symbol", "description", "homepage_url", "total_employees"]
_ACT_PREFERRED = re.compile(r"^([A-Z]+)\$([A-Z]*)$")  # ACT "KIM$L" == Massive "KIMpL"


def massive_ticker(symbol: str) -> str:
    """The universe's ACT-style symbol -> Massive's ticker (``KIM$L`` -> ``KIMpL``)."""
    match = _ACT_PREFERRED.match(symbol)
    return f"{match.group(1)}p{match.group(2)}" if match else symbol


def _text(value: object) -> str | None:
    text = " ".join(str(value or "").split())
    return text or None


def parse_overview(payload: bytes, symbol: str) -> pd.DataFrame:
    """One ticker's overview -> a one-row frame (``COLUMNS``). A response without a
    description (every ETF) still gives a row, with ``description`` None: the task stores it
    as a marker so the ticker is not asked again before the next refresh."""
    results = json.loads(payload).get("results") or {}
    employees = results.get("total_employees")
    row = {
        "symbol": act_symbol(str(results.get("ticker") or symbol)),
        "description": _text(results.get("description")),
        "homepage_url": _text(results.get("homepage_url")),
        "total_employees": int(employees) if isinstance(employees, int | float) else None,
    }
    return pd.DataFrame([row], columns=COLUMNS).astype(object)


class MassiveOverview(_Massive):
    """One ticker's description. Request key: the ACT-style symbol."""

    dataset = "ticker_overview"

    def fetch(self, request: FetchRequest) -> bytes | None:
        ticker = quote(massive_ticker(request.key), safe="")
        return self._get(OVERVIEW.format(ticker=ticker))

    def normalize(self, request: FetchRequest, payload: bytes) -> Normalized | None:
        return Normalized(
            session_date=None,
            tables={},
            parsed={"overview": parse_overview(payload, request.key)},
        )
