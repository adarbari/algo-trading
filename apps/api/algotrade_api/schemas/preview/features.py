"""``POST /features/check``: a formula type checked against the user's catalogue and sampled
on the latest session its inputs have."""

from datetime import date

from pydantic import BaseModel, Field

from algotrade_api.schemas.health import Schema


class CheckBody(BaseModel):
    expr: str = Field(description="the formula (the expression feature language)")
    user: str | None = Field(None, description="whose catalogue (default the API's)")
    sample: int = Field(5, ge=0, le=50, description="how many sample values to return")


class SampleValue(Schema):
    instrument_id: str
    value: float | int | bool | str | None


class ExpressionCheck(Schema):
    expr: str
    type: str = Field(description="num, bool, str or date")
    dtype: str
    categories: list[str] | None
    inputs: list[str]
    licence: str
    session: date | None = Field(description="the session sampled (None: nothing stored)")
    rows: int
    non_null: int
    sample: list[SampleValue]
