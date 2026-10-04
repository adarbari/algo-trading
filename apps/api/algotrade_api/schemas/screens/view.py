"""``/preferences/screeners/{id}/view``: a user's saved view of a screener's results."""

from pydantic import Field

from algotrade_api.schemas.health import Schema


class ScreenerView(Schema):
    screener_id: str
    saved: bool = Field(description="false: no view saved yet (the page uses its defaults)")
    columns: list[str] = Field(description="catalogue features added to the table, in order")
    sort: str | None = Field(description="a /screens/{id}/table sort (null: the default)")
    decisions: list[str] = Field(description="decisions shown (empty: the page's default)")
