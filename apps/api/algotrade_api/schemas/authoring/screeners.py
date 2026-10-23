"""``/screeners``: the bodies and answers of a user's rule-screen writes (reading a screen is
GraphQL)."""

from typing import Any, Literal

from pydantic import BaseModel, Field

from algotrade_api.schemas.health import Schema


class Finalised(Schema):
    screener_id: str
    version: int
    hash: str
    run_job_id: str | None = Field(
        None,
        description="the one-off run finalising started (poll GET /jobs/{id}); None when the "
        "results for this version were already stored or runs are off",
    )
    run_state: str | None = Field(
        None, description="that run's state (ready, queued, running, ...); None when none was asked"
    )


class Draft(Schema):
    screener_id: str
    document: dict[str, Any]


MAX_CHOICES = 50


class DraftChoice(BaseModel):
    """What the trader decided about one thing Describe it offered (ADR 0066): an unresolved
    term's reading (``choice_made``, ``picked`` the alternative's index) or a proposed formula
    (``formula_accepted`` / ``formula_skipped``, ``subject`` its name)."""

    event: Literal["choice_made", "formula_accepted", "formula_skipped"]
    subject: str = Field(max_length=120, description="the unresolved term, or the formula name")
    picked: int | None = Field(
        None, ge=0, le=1000, description="the alternative's index (choice_made only)"
    )
    feature: str | None = Field(
        None,
        max_length=120,
        description="the saved user feature's name, formula_accepted only (the trader may have "
        "renamed the proposed formula)",
    )


class DraftBody(BaseModel):
    document: dict[str, Any] = Field(
        description="the screen's TOML keys as JSON (the version is managed)"
    )
    draft_session_id: str | None = Field(
        None,
        max_length=64,
        description="the id a draft-from-text answer returned, when this screen came from it "
        "(ADR 0066); a hand-built screen sends none",
    )
    choices: list[DraftChoice] = Field(
        default_factory=list,
        max_length=MAX_CHOICES,
        description="the decisions the trader made on the draft's options, recorded with the "
        "save (ADR 0066); a re-sent one is the same event",
    )


class FinaliseBody(BaseModel):
    draft_session_id: str | None = Field(
        None,
        max_length=64,
        description="the id a draft-from-text answer returned, when this screen came from it "
        "(ADR 0066); a hand-built screen sends none",
    )
    choices: list[DraftChoice] = Field(
        default_factory=list,
        max_length=MAX_CHOICES,
        description="the decisions the trader made on the draft's options, recorded with the "
        "save (ADR 0066); a re-sent one is the same event",
    )


class CopyBody(BaseModel):
    preset: str = Field(description="the site rule-screen preset to extend (pinned)")
