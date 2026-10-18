"""FINRA consolidated short interest, twice a month: one payload per settlement date.

Dataset ``consolidatedShortInterest``, partition key ``settlementDate`` (the 15th and the last
business day of the month; the API holds 2017-12-29 onward). Request key: the settlement date,
ISO. One row per symbol (stocks and ETFs, exchange and OTC); a settlement date FINRA has not
published (or never held) answers nothing, so ``fetch`` is ``None`` and the task counts
``NO_DATA``.

``normalize`` emits ``events/short_interest`` rows keyed by ``symbol`` (the task resolves ids,
ADR 0018): ``ts`` the settlement date at midnight UTC; the task adds ``published`` and
``known_from`` (``tasks/shorting/schedule.py``). FINRA keeps only the latest revision of a
settlement date (``revision_flag`` marks a restated row), so the task never refetches a stored
date: the first-seen value is the point-in-time one.
"""

from datetime import UTC, date, datetime

import pandas as pd

from algotrade_sources.framework.base import FetchRequest, Normalized
from algotrade_sources.framework.http import Http
from algotrade_sources.vendors.finra import client

SOURCE = "finra_short_interest"
DATASET = "consolidated_short_interest"
API_DATASET = "consolidatedShortInterest"
TABLE = "events/short_interest"
COLUMNS = (
    "symbol",
    "ts",
    "short_position",
    "previous_short_position",
    "change_shares",
    "change_percent",
    "average_daily_volume",
    "days_to_cover",
    "market_class",
    "revision_flag",
    "split_flag",
)
_FIELDS = {  # FINRA field -> column
    "currentShortPositionQuantity": "short_position",
    "previousShortPositionQuantity": "previous_short_position",
    "changePreviousNumber": "change_shares",
    "changePercent": "change_percent",
    "averageDailyVolumeQuantity": "average_daily_volume",
    "daysToCoverQuantity": "days_to_cover",
    "marketClassCode": "market_class",
    "revisionFlag": "revision_flag",
    "stockSplitFlag": "split_flag",
}
_INTEGERS = ("short_position", "previous_short_position", "change_shares", "average_daily_volume")


def short_interest_rows(payload: bytes, settlement: date) -> pd.DataFrame:
    """The payload's records as ``COLUMNS`` rows of ``settlement``."""
    frame = pd.DataFrame(client.records(payload))
    if frame.empty or "symbolCode" not in frame.columns:
        return pd.DataFrame(columns=list(COLUMNS))
    frame = frame[frame["symbolCode"].notna() & (frame["symbolCode"].astype(str).str.strip() != "")]
    out = pd.DataFrame({"symbol": frame["symbolCode"].astype(str).str.strip()})
    for field, column in _FIELDS.items():
        out[column] = frame[field] if field in frame.columns else None
    for column in _INTEGERS:
        out[column] = pd.to_numeric(out[column], errors="coerce").round().astype("Int64")
    out["change_percent"] = pd.to_numeric(out["change_percent"], errors="coerce")
    out["days_to_cover"] = pd.to_numeric(out["days_to_cover"], errors="coerce")
    out["ts"] = pd.Timestamp(
        datetime(settlement.year, settlement.month, settlement.day, tzinfo=UTC)
    )
    out = out.drop_duplicates("symbol", keep="last").sort_values("symbol", kind="stable")
    return out[list(COLUMNS)].reset_index(drop=True)


class FinraShortInterest:
    """Implements ``sources.base.Source``. Request key: a settlement date (``"2026-09-30"``)."""

    name = SOURCE
    dataset = DATASET

    def __init__(self, http: Http) -> None:
        self._http = http  # paced by the shared ``finra`` limiter (sources.toml)

    def fetch(self, request: FetchRequest) -> bytes | None:
        return client.read_partition(self._http, API_DATASET, "settlementDate", request.key)

    def normalize(self, request: FetchRequest, payload: bytes) -> Normalized | None:
        settlement = date.fromisoformat(request.key)
        return Normalized(None, {TABLE: short_interest_rows(payload, settlement)})
