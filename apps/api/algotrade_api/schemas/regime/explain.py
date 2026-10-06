"""``POST /regime/explain``: one of ``question`` (only "what is happening?") or ``card`` (a card
key) in; the explanation, the allowed links it cited, whether its numbers checked out (else
``note`` says why and ``text`` is empty) and whether it came from the cache out."""

from pydantic import BaseModel, Field

from algotrade_api.schemas.health import Schema


class ExplainBody(BaseModel):
    question: str | None = Field(None, max_length=100, description='only "what is happening?"')
    card: str | None = Field(None, max_length=100, description="a regime card's key")


class Citation(Schema):
    title: str
    url: str


class RegimeExplanation(Schema):
    text: str = Field(description="plain-text explanation; empty when checked is false")
    citations: list[Citation] = Field(description="allowed links the explanation used")
    checked: bool = Field(description="every number in the text is one of the facts")
    note: str | None = Field(description="why the text is withheld, when it is")
    cached: bool = Field(description="read from the cache, not asked of the model")
