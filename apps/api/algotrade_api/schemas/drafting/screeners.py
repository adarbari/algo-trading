"""``POST /screeners/{id}/draft-from-text``: the sentence (and the Builder's current document,
whose criteria the model keeps unless the sentence changes them) in; the draft document, the
criteria dropped with their reasons and the model's notes out, plus the A / B / C contract
(ADR 0041, amended 2026-10-11): pending formulas with their dry run, the formulas dropped, the
missing features and the unresolved terms. Pending formulas are never in ``document``."""

from datetime import date
from typing import Any

from pydantic import BaseModel, Field

from algotrade.services.drafting.screens import MAX_TEXT
from algotrade_api.schemas.health import Schema


class DraftFromTextBody(BaseModel):
    text: str = Field(min_length=1, max_length=MAX_TEXT, description="the screen in plain English")
    document: dict[str, Any] | None = Field(
        None, description="the Builder's current document (its criteria are kept unless changed)"
    )


class DroppedCriterion(Schema):
    id: str
    field: str
    reason: str


class SampleValue(Schema):
    instrument_id: str
    value: Any


class FormulaDryRun(Schema):
    session: date | None = Field(description="the session read (null: not read, see missing)")
    missing: list[str] = Field(description="the inputs' tables with no data for the session")
    rows: int
    no_value_rate: float | None
    minimum: float | None
    maximum: float | None
    criterion_pass: int | None = Field(description="rows passing the formula's criterion")
    sample: list[SampleValue]


class DraftFormula(Schema):
    name: str
    expr: str
    dtype: str
    unit: str
    description: str
    null_meaning: str
    inputs: list[str]
    criterion: dict[str, Any] | None = Field(description="the criterion on the formula, pending")
    fingerprint: str
    dry_run: FormulaDryRun
    pending: bool = Field(description="true until the trader accepts it (never auto-applied)")


class DroppedFormula(Schema):
    name: str
    reason: str
    existing: str | None = Field(description="the feature it duplicates, when it does")


class MissingFeature(Schema):
    key: str | None = Field(description="an open backlog key, else null with new_key_slug")
    new_key_slug: str | None
    span: str
    description: str
    why_needed: str
    closest: list[str]
    feasibility: str = Field(description="ROLLUP_FROM_STORED, NEEDS_SOURCE or UNCLEAR")


class Alternative(Schema):
    label: str
    criterion: dict[str, Any]


class Unresolved(Schema):
    term: str
    span: str
    default_index: int
    alternatives: list[Alternative]


class ScreenDraft(Schema):
    screener_id: str
    document: dict[str, Any] = Field(description="the draft for the Builder (never saved here)")
    dropped: list[DroppedCriterion] = Field(description="proposed criteria the draft does not keep")
    notes: list[str] = Field(description="what the model could not map or assumed")
    formulas: list[DraftFormula] = Field(
        default_factory=list, description="B1: formulas offered, pending, not in the document"
    )
    formulas_dropped: list[DroppedFormula] = Field(default_factory=list)
    missing: list[MissingFeature] = Field(default_factory=list)
    unresolved: list[Unresolved] = Field(
        default_factory=list, description="ambiguous terms; the document has each default"
    )
    draft_session_id: str | None = Field(
        None,
        description="ties this draft to the screen later saved from it (ADR 0066); send it back "
        "with the save; null when feedback is not recorded",
    )
