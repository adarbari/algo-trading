"""FMP analyst estimates (``FmpAnalystEstimates``): the consensus forecast of a company's
revenue, EBITDA, EBIT, net income, SG&A and EPS, one row per fiscal period.

``/stable/analyst-estimates?symbol=S&period=annual|quarter&page=0&limit=N``. Each row carries
``symbol``, ``date`` (the fiscal period end, future ones included) and, per measure, ``<m>Low`` /
``<m>High`` / ``<m>Avg`` (``revenue``, ``ebitda``, ``ebit``, ``netIncome``, ``sgaExpense`` and
``eps``) and ``numAnalystsRevenue`` / ``numAnalystsEps``. Verified 2026-10-16 on a free key:
``period=annual`` answers; ``period=quarter`` answers 402 (a premium parameter), see
``fmp/probe.py``.

Request key: ``SYMBOL`` or ``SYMBOL:period`` (``AAPL:annual``, the default). ``normalize``
returns ``parsed["estimates"]`` (``ESTIMATE_COLUMNS``, ``fiscal_date`` a UTC midnight): nothing
is stored from here yet (the feature groups are a later PR); the history of an estimate starts
at the first fetch, the vendor's own history is never backdated (ADR 0068).
"""

import pandas as pd

from algotrade_sources.framework.base import FetchRequest, Normalized
from algotrade_sources.framework.http import Http
from algotrade_sources.vendors.fmp.client import SOURCE, rows, url, vendor_symbol

DATASET = "analyst_estimates"
PERIODS = ("annual", "quarter")
DEFAULT_LIMIT = 8  # periods asked for per request
MEASURES = {  # FMP's name -> ours
    "revenue": "revenue",
    "ebitda": "ebitda",
    "ebit": "ebit",
    "netIncome": "net_income",
    "sgaExpense": "sga_expense",
    "eps": "eps",
}
SIDES = ("low", "high", "avg")
ESTIMATE_COLUMNS = [
    "symbol",
    "period",
    "fiscal_date",
    *[f"{ours}_{side}" for ours in MEASURES.values() for side in SIDES],
    "num_analysts_revenue",
    "num_analysts_eps",
]


def parse_key(key: str) -> tuple[str, str]:
    """``SYMBOL`` or ``SYMBOL:period`` -> (symbol, period); an unknown period is a ValueError."""
    symbol, _, period = key.partition(":")
    period = period or "annual"
    if period not in PERIODS:
        raise ValueError(f"period must be one of {PERIODS}, got {period!r}")
    return symbol, period


def parse_estimates(payload: bytes, period: str) -> pd.DataFrame:
    """The records -> ``ESTIMATE_COLUMNS``, oldest period first; a row with no ``date`` or
    ``symbol`` is dropped, a repeated (symbol, date) kept once."""
    records = rows(payload)
    frame = pd.DataFrame(index=range(len(records)))
    frame["symbol"] = [str(r.get("symbol") or "").strip().upper() for r in records]
    frame["period"] = period
    dates = [r.get("date") for r in records]
    frame["fiscal_date"] = pd.to_datetime(pd.Series(dates), utc=True, errors="coerce")
    for theirs, ours in MEASURES.items():
        for side in SIDES:
            values = pd.Series([r.get(f"{theirs}{side.capitalize()}") for r in records])
            frame[f"{ours}_{side}"] = pd.to_numeric(values, errors="coerce")
    for field in ("Revenue", "Eps"):
        counts = pd.Series([r.get(f"numAnalysts{field}") for r in records])
        frame[f"num_analysts_{field.lower()}"] = pd.to_numeric(counts, errors="coerce")
    kept = frame[(frame["symbol"] != "") & frame["fiscal_date"].notna()]
    ordered = kept.drop_duplicates(["symbol", "fiscal_date"]).sort_values("fiscal_date")
    return ordered[ESTIMATE_COLUMNS].reset_index(drop=True)


class FmpAnalystEstimates:
    """Implements ``sources.base.Source``. Request key: ``SYMBOL`` or ``SYMBOL:period``."""

    name = SOURCE
    dataset = DATASET

    def __init__(self, http: Http) -> None:
        self._http = http  # paced by the shared ``fmp`` limiter (sources.toml)

    def fetch(self, request: FetchRequest) -> bytes | None:
        symbol, period = parse_key(request.key)
        return self._http.get(
            url(
                "analyst-estimates",
                symbol=vendor_symbol(symbol),
                period=period,
                page=0,
                limit=DEFAULT_LIMIT,
            )
        )

    def normalize(self, request: FetchRequest, payload: bytes) -> Normalized | None:
        _, period = parse_key(request.key)
        return Normalized(
            session_date=request.session_date,
            tables={},
            notes={},
            parsed={"estimates": parse_estimates(payload, period)},
        )
