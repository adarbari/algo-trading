"""FINRA Reg SHO daily short-sale volume: one payload per trade date.

Dataset ``regShoDaily``, partition key ``tradeReportDate`` (the API serves a rolling year).
Request key: the trade date, ISO. FINRA reports one row per symbol and reporting facility
(``NCTRF``, ``NQTRF``, ``NYTRF``, ``ADF``): off-exchange prints only, so the short share is a
venue-biased proxy of short selling, not short interest.

``normalize`` emits ``events/short_volume`` rows keyed by ``symbol`` (ids resolved by the
task), the facilities summed into one row per symbol: ``ts`` the trade date at midnight UTC (the
task adds ``known_from``, ``tasks/shorting/schedule.py``). A trade date with no rows (weekend,
holiday, not published yet) answers nothing: ``fetch`` is ``None``.
"""

from datetime import UTC, date, datetime

import pandas as pd

from algotrade_sources.framework.base import FetchRequest, Normalized
from algotrade_sources.framework.http import Http
from algotrade_sources.vendors.finra import client

SOURCE = "finra_short_volume"
DATASET = "reg_sho_daily"
API_DATASET = "regShoDaily"
TABLE = "events/short_volume"
COLUMNS = (
    "symbol",
    "ts",
    "short_volume",
    "short_exempt_volume",
    "total_volume",
    "facilities",
)
_SYMBOL = "securitiesInformationProcessorSymbolIdentifier"
_SUMS = {
    "shortParQuantity": "short_volume",
    "shortExemptParQuantity": "short_exempt_volume",
    "totalParQuantity": "total_volume",
}


def short_volume_rows(payload: bytes, trade_date: date) -> pd.DataFrame:
    """The payload's records summed over facilities, as ``COLUMNS`` rows of ``trade_date``."""
    frame = pd.DataFrame(client.records(payload))
    if frame.empty or _SYMBOL not in frame.columns:
        return pd.DataFrame(columns=list(COLUMNS))
    frame = frame[frame[_SYMBOL].notna() & (frame[_SYMBOL].astype(str).str.strip() != "")]
    work = pd.DataFrame({"symbol": frame[_SYMBOL].astype(str).str.strip()})
    for field, column in _SUMS.items():
        work[column] = pd.to_numeric(frame[field], errors="coerce") if field in frame else 0
    work["facilities"] = 1
    out = work.groupby("symbol", sort=True).sum(min_count=1).reset_index()
    for column in (*_SUMS.values(), "facilities"):
        out[column] = out[column].round().astype("Int64")
    out["ts"] = pd.Timestamp(
        datetime(trade_date.year, trade_date.month, trade_date.day, tzinfo=UTC)
    )
    return out[list(COLUMNS)]


class FinraShortVolume:
    """Implements ``sources.base.Source``. Request key: a trade date (``"2026-10-16"``)."""

    name = SOURCE
    dataset = DATASET

    def __init__(self, http: Http) -> None:
        self._http = http  # paced by the shared ``finra`` limiter (sources.toml)

    def fetch(self, request: FetchRequest) -> bytes | None:
        return client.read_partition(self._http, API_DATASET, "tradeReportDate", request.key)

    def normalize(self, request: FetchRequest, payload: bytes) -> Normalized | None:
        trade_date = date.fromisoformat(request.key)
        return Normalized(None, {TABLE: short_volume_rows(payload, trade_date)})
