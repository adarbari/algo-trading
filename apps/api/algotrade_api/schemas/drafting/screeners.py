"""``POST /screeners/{id}/draft-from-text``: the sentence (and the Builder's current document,
whose criteria the model keeps unless the sentence changes them) in; the draft document, the
criteria dropped with their reasons and the model's notes out, plus the A / B / C contract
(ADR 0041, amended 2026-10-11): pending formulas with their dry run, the formulas dropped, the
missing features and the unresolved terms, and the suggested checks (soft or score, offered
not applied) with those dropped. Pending formulas and suggestions are never in ``document``.
The explained parts (same amendment, 2026-10-11): ``sentence`` (the whitespace-normalised text the
parts' offsets count in) and ``parts``, each the trader's own words (the server's slice of the
sentence), the model's reading when it checks out, the kind the server decided and the ids of the
items of this draft that belong to it; ``parts`` is null when the model gave none (the panel then
shows the draft as before).
``POST /screeners/{id}/draft-part`` (ADR 0041, amended 2026-10-12): the trader retypes the words of
one part. The body is the draft the browser holds (its fields as served, ``document`` the Builder's
current one) and which part's words become what; the answer is the whole merged draft and the id
of the part it replaced, which the browser swaps in whole. At the per-user daily limit the answer
is a 429 with ``LimitReached`` (its ``code`` is what the web shows the limit state on)."""

from datetime import date
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field

from algotrade.services.drafting.parts.model import MAX_PARTS, MAX_WORDS
from algotrade.services.drafting.redraft.request import MAX_ITEMS
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


class DraftSampleValue(Schema):
    instrument_id: str
    value: Any


class FormulaDryRun(Schema):
    session: date | None = Field(description="the session read (null: not read: no data for it)")
    rows: int
    no_value_rate: float | None
    minimum: float | None
    maximum: float | None
    criterion_pass: int | None = Field(description="rows passing the formula's criterion")
    sample: list[DraftSampleValue]


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
    id: str = Field(
        description="p1... from the model; g1... a gap; kept / unplaced: catch-alls with no words"
    )
    words: str = Field(description="the sentence's own words for this part; empty for a catch-all")
    start: int = Field(description="offset of words in sentence, in UTF-16 code units (JS slice)")
    end: int = Field(description="end offset of words in sentence, in UTF-16 code units")
    reading: str | None = Field(
        description="what the words were read as: the model's line (reading_source model), or "
        "the server's own, built from the part's phrasebook entry (a draft made without the "
        "model); null when the model gave none or its numbers disagree with the part's "
        "criteria (then reading_source is server)"
    )
    reading_source: Literal["model", "server"]
    kind: Literal["applied", "formula", "needs_choice", "not_available", "not_understood"] = Field(
        description="decided by the server from what the part holds, never by the model"
    )
    origin: Literal["words", "gap", "kept", "unplaced"] = Field(
        description="words: a part of the model, located in the sentence; gap: words no part "
        "covers; kept: criteria carried over from the Builder's document; unplaced: items tied "
        "to no words (kept and unplaced have no words)"
    )
    criteria: list[str] = Field(description="ids of criteria in the draft document")
    dropped: list[str] = Field(description="ids of the criteria dropped")
    formulas: list[str] = Field(description="names of pending formulas")
    unresolved: list[str] = Field(description="terms of the unresolved readings")
    missing: list[str] = Field(description="keys (or new slugs) of the missing-feature requests")
    suggestions: list[str] = Field(description="ids of suggestions")
    rank: bool = Field(description="true when the document's tie-break belongs to this part")
    join: Literal["and", "or", "and_not"] | None = Field(
        default=None,
        description="how this part relates to the one before it, read by the server from the "
        "connector between them (but, or, except...); null when none lies between them",
    )
    join_words: str = Field(
        default="", description="the sentence's own words of that connector; empty when no join"
    )


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
        default_factory=str,  # not a literal default: the web client types those as required
        description="the whitespace-normalised sentence the parts' offsets count in",
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


Line = Annotated[str, Field(max_length=MAX_TEXT)]


class DraftPartBody(BaseModel):
    """The draft the browser holds, and which part's words to retype. Nothing in it is trusted:
    the server re-checks every part's words against the sentence and every id against the items
    (``services.drafting.redraft.request``); a failed check is a 400."""

    draft_session_id: str | None = Field(
        None,
        max_length=64,
        description="the id of the draft being worked on (ADR 0066), so the re-draft is an "
        "event of the same session; an unknown or foreign id starts a new one",
    )
    sentence: str = Field(
        min_length=1, max_length=MAX_TEXT, description="the draft's `sentence`, as served"
    )
    document: dict[str, Any] = Field(
        description="the Builder's current document: the trader's edits included"
    )
    parts: list[Part] = Field(max_length=MAX_PARTS + 2, description="the draft's `parts`")
    part_id: str = Field(
        min_length=1, max_length=16, description="the part whose words are retyped"
    )
    new_words: str = Field(
        min_length=1, max_length=MAX_WORDS, description="what the part's words become"
    )
    dropped: list[DroppedCriterion] = Field(default_factory=list, max_length=MAX_ITEMS)
    notes: list[Line] = Field(default_factory=list, max_length=MAX_ITEMS)
    formulas: list[DraftFormula] = Field(default_factory=list, max_length=MAX_ITEMS)
    formulas_dropped: list[DroppedFormula] = Field(default_factory=list, max_length=MAX_ITEMS)
    missing: list[MissingFeature] = Field(default_factory=list, max_length=MAX_ITEMS)
    unresolved: list[Unresolved] = Field(default_factory=list, max_length=MAX_ITEMS)
    suggestions: list[Suggestion] = Field(default_factory=list, max_length=MAX_ITEMS)
    suggestions_dropped: list[DroppedSuggestion] = Field(default_factory=list, max_length=MAX_ITEMS)


class DraftPartResult(Schema):
    draft: ScreenDraft = Field(
        description="the whole draft with the part re-drafted and every other part as it was; "
        "the browser replaces its draft with it (`sentence` has the new words in place)"
    )
    replaced_part_id: str = Field(description="the part that was re-drafted")


class LimitReached(BaseModel):
    """The 429 of a user at their daily limit of part re-drafts (not a rate limit: it clears
    when the exchange day turns)."""

    detail: str
    code: Literal["part_redraft_limit"]
    limit: int = Field(description="part re-drafts a user may ask per exchange day")
    retry_after_s: int = Field(description="seconds until the exchange day turns")
