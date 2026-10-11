"""``/screeners``: the bodies and answers of a user's rule-screen writes (reading a screen is
GraphQL)."""

from typing import Any

from pydantic import BaseModel, Field

from algotrade_api.schemas.health import Schema


class Finalised(Schema):
    screener_id: str
    version: int
    hash: str


class Draft(Schema):
    screener_id: str
    document: dict[str, Any]


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


class FinaliseBody(BaseModel):
    draft_session_id: str | None = Field(
        None,
        max_length=64,
        description="the id a draft-from-text answer returned, when this screen came from it "
        "(ADR 0066); a hand-built screen sends none",
    )


class CopyBody(BaseModel):
    preset: str = Field(description="the site rule-screen preset to extend (pinned)")
