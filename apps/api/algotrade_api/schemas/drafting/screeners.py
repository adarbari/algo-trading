"""``POST /screeners/{id}/draft-from-text``: the sentence (and the Builder's current document,
whose criteria the model keeps unless the sentence changes them) in; the draft document, the
criteria dropped with their reasons and the model's notes out."""

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


class ScreenDraft(Schema):
    screener_id: str
    document: dict[str, Any] = Field(description="the draft for the Builder (never saved here)")
    dropped: list[DroppedCriterion] = Field(description="proposed criteria the draft does not keep")
    notes: list[str] = Field(description="what the model could not map or assumed")
