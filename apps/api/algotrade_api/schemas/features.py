"""``/features``: the feature catalogue and one feature's distribution."""

from datetime import date

from pydantic import Field

from algotrade_api.schemas.health import Schema


class Feature(Schema):
    name: str
    kind: str
    source: str
    dtype: str
    description: str
    null_meaning: str
    version: int | None
    rollup: str | None
    inputs: list[str]
    unit: str | None
    range: list[float] | None


class Bin(Schema):
    lo: float
    hi: float
    count: int


class Category(Schema):
    value: str
    count: int


class Distribution(Schema):
    name: str
    dtype: str
    session: date
    count: int = Field(description="instruments with a row (null or not)")
    nulls: int
    quantiles: dict[str, float] = Field(description="'0.5' -> median, ... (numeric features)")
    histogram: list[Bin] = Field(description="20 equal-width bins (numeric features)")
    categories: list[Category] = Field(description="the most frequent values (other features)")
