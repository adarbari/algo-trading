"""``PUT /preferences/ideas``: the user's screener priority for the Ideas list."""

from pydantic import BaseModel, Field

from algotrade_api.schemas.health import Schema


class IdeasPriorityBody(BaseModel):
    priority: list[str] = Field(description="screener ids, highest priority first")


class IdeasPriority(Schema):
    priority: list[str]
