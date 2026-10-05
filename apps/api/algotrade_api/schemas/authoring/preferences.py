"""``PUT /preferences/ideas``: the user's screener priority for the Ideas list;
``PUT /preferences/screeners/{id}/view``: their view of one screener's results."""

from pydantic import BaseModel, Field

from algotrade_api.schemas.health import Schema


class IdeasPriorityBody(BaseModel):
    priority: list[str] = Field(description="screener ids, highest priority first")


class IdeasPriority(Schema):
    priority: list[str]


class ScreenerViewBody(BaseModel):
    columns: list[str] = Field(description="catalogue features added to the table, in order")
    sort: str | None = Field(
        None, description="a /screens/{id}/table sort ('-' prefix: descending); null: default"
    )
    decisions: list[str] = Field(description="decisions shown (empty: the page's default)")
