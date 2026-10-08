"""``POST /screeners/preview``: an unsaved rule-screen draft evaluated on the latest closed
session (summary, decisions, funnel, coverage, top rows shaped as the review table's, and the
changes against the saved run)."""

from datetime import date
from typing import Any

from pydantic import BaseModel, Field

from algotrade.services.read.availability.cause import ADMIN_CAUSE, AUDIT
from algotrade_api.schemas.availability import Unavailable
from algotrade_api.schemas.health import Schema


class PreviewBody(BaseModel):
    spec: dict[str, Any] = Field(description="the draft rule screen (as the Builder holds it)")
    user: str | None = Field(
        None,
        description="whose catalogue and presets (default: the caller's; another: admins only)",
    )
    limit: int = Field(
        50,
        ge=0,
        le=1000,
        description="the fewest top rows; every row not rejected comes too (up to 1000)",
    )


class FunnelStep(Schema):
    criterion_id: str
    field: str
    mode: str
    entering: int = Field(description="rows still in after every earlier step")
    passed: int
    near: int
    failed: int
    missing: int
    remaining: int = Field(
        description="what the next step sees: passed + near (+ no value, for a soft step)"
    )


class CriterionValue(Schema):
    criterion_id: str
    field: str
    mode: str
    value: Any
    outcome: str = Field(description="PASS, NEAR, FAIL or MISSING")
    distance: float | None
    normalised: float | None
    penalty: float


class PreviewRow(Schema):
    instrument_id: str
    symbol: str | None
    name: str | None = Field(description="the company or fund name (the universe snapshot's)")
    rank: int = Field(description="1 = best: score, then the tie-break, then instrument id")
    decision: str = Field(description="QUALIFIED, WATCH, LIQUIDITY_RISK, EVENT_RISK or REJECT")
    score: float | None = Field(description="100 minus the penalties, clipped to 0..100")
    flags: list[str] = Field(description="warnings that never change the decision")
    reasons: list[str] = Field(description="why the decision is not QUALIFIED (`no <field>` too)")
    columns: dict[str, Any] = Field(description="the screen's display columns: name -> value")
    criteria: list[CriterionValue]


class NarrowMiss(Schema):
    instrument_id: str
    criterion_id: str
    field: str
    value: Any
    threshold: float | None = Field(description="the threshold missed (nearer bound: between)")
    distance: float | None = Field(description="how far from the threshold, in the field's unit")
    normalised: float | None = Field(description="distance / tolerance width, 0..1")


class PreviewSummary(Schema):
    rows: int
    passed: int
    missing: int = Field(
        description="gating values missing where the funnel reached them, per row and criterion"
    )
    missing_reasons: dict[str, int] = Field(description="`no <field>` -> rows")
    narrow_misses: list[NarrowMiss]


class PreviewCoverage(Schema):
    coverage: str = Field(description="COMPLETE, PARTIAL, UNIVERSE_INCOMPLETE or EMPTY_SELECTION")
    base: int = Field(description="instruments the selection saw")
    selected: int
    processed: int = Field(description="rows evaluated (none is skipped since ADR 0030)")
    skipped: int = Field(description="always 0 for a rule screen; kept for stored runs")
    coverage_pct: float = Field(description="processed / selected")
    min_coverage: float = Field(description="below this the run is PARTIAL")
    selection: dict[str, Any] = Field(
        description="the selection's audit (without the tables it went without, unless an admin)",
        json_schema_extra={ADMIN_CAUSE: AUDIT},
    )
    missing_tables: list[str] = Field(
        description="tables with no rows for the session (legacy, admins only: empty for "
        "anyone else; `unavailable` says what they leave out)",
        json_schema_extra={ADMIN_CAUSE: []},
    )
    unavailable: list[Unavailable] = Field(
        default_factory=list,
        description="what the tables with no rows for the session leave out, in public words",
    )
    pre_snapshot: bool = Field(description="the reference snapshot is after the session")
    universe_snapshot: date


class PreviewChanges(Schema):
    run_id: str = Field(description="the screener's saved run compared with")
    session: date = Field(description="its session (the one the draft was evaluated on)")
    entered: list[str] = Field(description="tickers the draft picks that the run did not")
    left: list[str] = Field(description="tickers the run picked that the draft does not")


class PreviewCriterion(Schema):
    id: str
    field: str = Field(description="the catalogue field it judges")
    mode: str = Field(description="hard, soft or score")


class PreviewColumn(Schema):
    name: str
    field: str = Field(description="the catalogue field it shows")


class ScreenPreview(Schema):
    screener_id: str
    user: str
    config_hash: str
    session: date = Field(description="the session evaluated")
    last_closed: date = Field(description="the latest closed exchange session")
    summary: PreviewSummary
    decisions: dict[str, int]
    funnel: list[FunnelStep]
    coverage: PreviewCoverage
    total: int
    criteria: list[PreviewCriterion] = Field(description="the draft's, in funnel order")
    display_columns: list[PreviewColumn] = Field(description="the draft's [columns]")
    rows: list[PreviewRow]
    cached: bool = Field(description="the field frame came from the in-process cache")
    changes: PreviewChanges | None = Field(
        description="against the screener's saved run for the session; null: none saved"
    )
