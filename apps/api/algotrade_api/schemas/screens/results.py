"""``/screens``: screener configs and a screen's results."""

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
