"""``/ideas``: the best tickers over the user's rule screens."""

from datetime import date
from typing import Any

from algotrade_api.schemas.health import Schema


class IdeaCriterion(Schema):
    criterion_id: str
    field: str
    outcome: str
    value: float | str | None
    distance: float | None


class IdeaPick(Schema):
    decision: str
    score: float | None
    reasons: str
    config_id: str
    config_version: int | None
    user: str
    session: date
    criteria: list[IdeaCriterion]
    columns: dict[str, Any]
    criterion_values: dict[str, Any]
    flags: list[str]


class Idea(Schema):
    rank: int
    instrument_id: str
    symbol: str | None
    picks: list[IdeaPick]
    next_earnings_date: date | None
    days_to_earnings: int | None
    closest_expiry_dte: int | None
    earnings_before_expiry: bool | None


class IdeaScreener(Schema):
    config_id: str
    user: str | None
    name: str
    version: int | None


class Ideas(Schema):
    session: date | None  # None: no screener has stored results yet
    priority: list[str]
    screeners: list[IdeaScreener]
    total: int
    items: list[Idea]
