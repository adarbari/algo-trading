"""``/explore``: the ticker table (tickers x catalogue columns) and multi-ticker compare."""

from datetime import date
from typing import Any

from pydantic import Field

from algotrade_api.schemas.health import Page, Schema


class TickerTable(Schema):
    session: date
    snapshot_date: date
    pre_snapshot: bool
    columns: list[str] = Field(description="the requested feature columns, in order")
    sort: str = Field(description="the sort column ('-' prefix: descending; nulls last)")
    missing: list[str] = Field(
        description="tables with no partition for the session (their columns are null)"
    )
    page: Page[dict[str, Any]]


class Compared(Schema):
    instrument_id: str
    symbol: str | None


class FeatureRow(Schema):
    feature: str
    dtype: str
    values: dict[str, Any]


class FeatureComparison(Schema):
    session: date
    instruments: list[Compared]
    missing: list[str]
    rows: list[FeatureRow]


class PriceComparison(Schema):
    instruments: list[Compared]
    adjustment: str
    rebase: float | None = Field(
        description="each series / its first close x rebase (null: raw closes)"
    )
    start: date
    end: date
    dates: list[date] = Field(description="the union of the instruments' sessions")
    series: dict[str, list[float | None]] = Field(
        description="instrument id -> close per date (null: no bar)"
    )
