"""``POST /screeners/{id}/draft-from-text``: the sentence (and the Builder's current document,
whose criteria the model keeps unless the sentence changes them) in; the draft document, the
criteria dropped with their reasons and the model's notes out, plus the A / B / C contract
(ADR 0041, amended 2026-10-11): pending formulas with their dry run, the formulas dropped, the
missing features and the unresolved terms, and the suggested checks (soft or score, offered
not applied) with those dropped. Pending formulas and suggestions are never in ``document``.
The explained parts (same amendment, 2026-10-12): ``sentence`` (the whitespace-normalised text the
parts' offsets count in) and ``parts``, each the trader's own words (the server's slice of the
sentence), the model's reading when it checks out, the kind the server decided and the ids of the
items of this draft that belong to it; ``parts`` is null when the model gave none (the panel then
shows the draft as before)."""

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field

from algotrade.services.drafting.screens import MAX_TEXT
from algotrade_api.schemas.health import Schema


class DraftFromTextBody(BaseModel):
    text: str = Field(min_length=1, max_length=MAX_TEXT, description="the screen in plain English")
    document: dict[str, Any] | None = Field(
        None, description="the Builder's current document (its criteria are kept unless changed)"
    )
    draft_session_id: str | None = Field(
        None,
        max_length=64,
        description="the id of the previous answer for this screen, so successive descriptions "
        "of one screen stay in one session (ADR 0066); an unknown, foreign or already saved "
        "session starts a new one",
    )


class DroppedCriterion(Schema):
    id: str
    field: str
    reason: str


class SampleValue(Schema):
    instrument_id: str
    value: Any


class FormulaDryRun(Schema):
    session: date | None = Field(description="the session read (null: not read: no data for it)")
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
    text: str
    criterion: dict[str, Any]


class Unresolved(Schema):
    term: str
    span: str
    default_index: int
    alternatives: list[Alternative]


class Suggestion(Schema):
    id: str = Field(description="the server's id (s1, s2...), what a part's suggestions name")
    criterion: dict[str, Any] = Field(
        description="a soft or score criterion, never in the document"
    )
    why: str = Field(description="the short reason, from the caveat or situation")
    source: str | None = Field(description="the field guide entry or field that raised it")


class DroppedSuggestion(Schema):
    field: str
    reason: str


class Part(Schema):
    id: str = Field(description="p1... from the model; g1... a gap; kept / unplaced: catch-alls")
    words: str = Field(description="the sentence's own words for this part; empty for a catch-all")
    start: int = Field(description="offset of words in sentence, in UTF-16 code units (JS slice)")
    end: int = Field(description="end offset of words in sentence, in UTF-16 code units")
    reading: str | None = Field(
        description="what the model read the words as; null when it gave none or its numbers "
        "disagree with the part's criteria (then reading_source is server)"
    )
    reading_source: Literal["model", "server"]
    kind: Literal["applied", "formula", "needs_choice", "not_available", "not_understood"] = Field(
        description="decided by the server from what the part holds, never by the model"
    )
    origin: Literal["words", "kept", "unplaced"] = Field(
        description="words: located in the sentence; kept: criteria carried over from the "
        "Builder's document; unplaced: tied to no words"
    )
    criteria: list[str] = Field(description="ids of criteria in the draft document")
    dropped: list[str] = Field(description="ids of the criteria dropped")
    formulas: list[str] = Field(description="names of pending formulas")
    unresolved: list[str] = Field(description="terms of the unresolved readings")
    missing: list[str] = Field(description="keys (or new slugs) of the missing-feature requests")
    suggestions: list[str] = Field(description="ids of suggestions")
    rank: bool = Field(description="true when the document's tie-break belongs to this part")


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
    suggestions: list[Suggestion] = Field(
        default_factory=list,
        description="protective checks offered (soft or score), never in the document: the "
        "trader accepts or skips each",
    )
    suggestions_dropped: list[DroppedSuggestion] = Field(default_factory=list)
    sentence: str = Field(
        "", description="the whitespace-normalised sentence the parts' offsets count in"
    )
    parts: list[Part] | None = Field(
        None,
        description="the explained parts, in sentence order (catch-alls last); null when the "
        "model gave none: show the draft without them",
    )
    draft_session_id: str | None = Field(
        None,
        description="ties this draft to the screen later saved from it (ADR 0066); send it back "
        "with the save; null when feedback is not recorded",
    )
