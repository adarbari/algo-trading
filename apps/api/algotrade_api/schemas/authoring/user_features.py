"""``POST /features/user``: a named user expression feature (body and result)."""

from pydantic import BaseModel, Field

from algotrade_api.schemas.health import Schema


class UserFeatureBody(BaseModel):
    name: str = Field(description="the feature's name: selected as feature.<name>")
    theme: str = Field("builder", description="config/users/<u>/features/<theme>.toml")
    expr: str
    dtype: str
    unit: str
    description: str
    null_meaning: str
    kind: str | None = None
    categories: list[str] | None = None
    valid_range: list[float | None] | None = None
    params: dict[str, float | str | bool] | None = None


class SavedFeature(Schema):
    name: str
    field: str
    theme: str
    dtype: str
    kind: str
    inputs: list[str]
