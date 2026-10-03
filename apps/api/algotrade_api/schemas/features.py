"""``/features``: the feature catalogue and one feature's distribution."""

from datetime import date

from pydantic import Field

from algotrade_api.schemas.health import Schema


class Feature(Schema):
    name: str = Field(description="the selection field (rollup.<group>@v<N>.<column>, ...)")
    kind: str = Field(description="instrument, or the feature's kind (window, chain, ...)")
    source: str
    dtype: str
    description: str
    null_meaning: str
    version: int | None
    group: str | None
    key: str | None = Field(description="the feature key <group>.<column>@v<N>")
    inputs: list[str]
    unit: str | None
    range: list[float | None] | None = Field(description="plausible (min, max)")
    categories: list[str]
    scope: str = Field(description="site, or user: one of the caller's own expression features")
    owner: str | None = Field(description="the user who declared it (scope user)")


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
