"""``/universe`` and ``/review``: the filtered universe page and the owner's review lists."""

from datetime import date
from typing import Any

from algotrade_api.schemas.health import Page, Schema


class UniverseRow(Schema):
    instrument_id: str
    symbol: str | None
    company_name: str | None
    security_type: str | None
    asset_class: str | None
    exchange: str | None
    optionable: bool | None
    is_leveraged: bool | None
    is_inverse: bool | None
    leverage: float | None
    in_sp500: bool | None
    sector: str | None
    industry: str | None
    liquidity_class: str | None


class UniversePage(Schema):
    session: date
    snapshot_date: date
    pre_snapshot: bool
    version: str
    missing: list[str]
    page: Page[UniverseRow]


class ReviewList(Schema):
    session: date | None
    source: str
    items: list[dict[str, Any]]
