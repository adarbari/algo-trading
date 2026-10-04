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
    config_id: str
    user: str
    config_version: int | None
    session: date
    decision: str
    score: float | None
    tier: str | None
    klass: str | None
    reasons: str
    criteria: list[IdeaCriterion]
    columns: dict[str, Any]


class Idea(Schema):
    rank: int
    instrument_id: str
    symbol: str | None
    picks: list[IdeaPick]
    next_earnings_date: date | None
    days_to_earnings: int | None
    closest_expiry_dte: int | None


class Ideas(Schema):
    session: date
    priority: list[str]
    total: int
    items: list[Idea]
