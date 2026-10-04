"""``GET /screens/{id}/table``: a rule screen's latest run as a review table (ADR 0031)."""

from datetime import date
from typing import Any

from pydantic import Field

from algotrade_api.schemas.health import Page, Schema


class CriterionHeader(Schema):
    criterion_id: str
    field: str
    mode: str = Field(description="hard, soft or score, as the screen states it")


class CriterionResult(Schema):
    value: float | str | None
    outcome: str = Field(description="PASS, NEAR, FAIL or MISSING")


class ScreenTableRow(Schema):
    rank: int = Field(description="1 = best: score, then the tie-break, then the instrument id")
    instrument_id: str
    symbol: str | None
    name: str | None
    decision: str
    score: float | None
    reasons: str
    flags: list[str]
    change: str | None = Field(
        description="new or dropped against the previous run (null: same, or no previous run)"
    )
    previous_decision: str | None = Field(
        description="the decision in the previous run (null: none, or not in it)"
    )
    criteria: dict[str, CriterionResult] = Field(description="criterion id -> what it judged")
    columns: dict[str, Any] = Field(description="the screen's display columns")
    features: dict[str, Any] = Field(description="the requested catalogue features, by name")


class ScreenTable(Schema):
    config_id: str
    user: str
    session: date
    previous_session: date | None = Field(description="null: the screen has no earlier run")
    run_id: str
    decisions: dict[str, int] = Field(description="every decision of the run, before any filter")
    changes: dict[str, int] = Field(description="new / dropped counts, before any filter")
    criteria: list[CriterionHeader] = Field(description="the screen's criteria, in its order")
    column_names: list[str] = Field(description="the screen's display columns, in its order")
    feature_columns: list[str] = Field(description="the requested catalogue features, in order")
    missing: list[str] = Field(
        description="tables with no partition for the session (their features are null)"
    )
    page: Page[ScreenTableRow]
