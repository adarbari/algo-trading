"""``/screens``: screener configs and a screen's results; ``/ideas``: the best tickers."""

from datetime import date
from typing import Any

from algotrade_api.schemas.configs import ConfigSummary
from algotrade_api.schemas.health import Page, Schema


class ScreenConfig(Schema):
    config: ConfigSummary
    latest_run: str | None
    latest_session: date | None
    latest_status: str | None


class ScreenRow(Schema):
    instrument_id: str
    symbol: str | None
    decision: str
    score: float | None
    reasons: str | None
    values: dict[str, Any]


class ScreenResults(Schema):
    config_id: str
    user: str
    session: date
    run_id: str | None
    decisions: dict[str, int]
    audit: dict[str, Any]
    page: Page[ScreenRow]


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
    klass: str | None
    tier: str | None
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
