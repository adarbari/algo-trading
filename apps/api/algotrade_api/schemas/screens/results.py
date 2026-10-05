"""``/screens``: screener configs and a screen's results."""

from datetime import date
from typing import Any

from pydantic import Field

from algotrade_api.schemas.health import Page, Schema


class ConfigSummary(Schema):
    config_id: str
    scope: str = Field(description="site (a preset) or the user's id")
    kind: str | None = Field(description="strategy | screener (null when it does not resolve)")
    impl: str | None
    selection: str | None = Field(description="the named selection, or inline")
    hash: str | None = Field(description="fingerprint of the resolved config")
    error: str | None = Field(description="why the config does not resolve")


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
