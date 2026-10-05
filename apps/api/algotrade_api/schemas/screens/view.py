"""``/preferences/screeners/{id}/view``: a user's saved view of a screener's results."""

from pydantic import Field

from algotrade_api.schemas.health import Schema


class ScreenerView(Schema):
    screener_id: str
    name: str | None = Field(description="the view's name (null: the screener's default view)")
    saved: bool = Field(description="false: this view is not saved yet (the page uses defaults)")
    columns: list[str] = Field(description="catalogue features added to the table, in order")
    sort: str | None = Field(description="a /screens/{id}/table sort (null: the default)")
    decisions: list[str] = Field(description="decisions shown (empty: the page's default)")
    names: list[str] = Field(description="the user's named views of this screener, sorted")


class ViewNames(Schema):
    names: list[str] = Field(description="the user's named views of this screener, sorted")
