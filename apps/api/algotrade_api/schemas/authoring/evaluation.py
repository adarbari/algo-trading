"""``PUT /evaluation/split``: the user's train / test split (``split_from``, or null to clear)."""

from datetime import date

from pydantic import BaseModel, Field

from algotrade_api.schemas.health import Schema


class EvaluationSplitBody(BaseModel):
    split_from: date | None = Field(
        description="the first session of the test slice (a stored session); null: clear it"
    )


class EvaluationSplitSaved(Schema):
    split_from: date | None = Field(description="the split now saved (null: none)")
