"""``PUT`` / ``DELETE /preferences/views/{scope}/view``: a user's views of a table."""

from pydantic import BaseModel, Field

from algotrade_api.schemas.health import Schema


class TableViewBody(BaseModel):
    columns: list[str] = Field(description="catalogue features added to the table, in order")
    sort: str | None = Field(
        None, description="a column id ('-' prefix: descending); null: the table's default"
    )
    decisions: list[str] = Field(description="decisions shown (empty: the page's default)")
    narrow_columns: list[str] | None = Field(
        default=None,
        description="table column ids added back on a narrow (phone) table; absent: kept as saved",
    )
    filters: str | None = Field(
        default=None,
        description="the filter bar's `f` string (ADR 0082); absent or empty: no filters",
    )


class TableView(Schema):
    scope: str = Field(description="the table: screener:<id> for a screener's results")
    name: str | None = Field(description="the view's name (null: the table's default view)")
    saved: bool = Field(description="false: this view is not saved yet (the page uses defaults)")
    columns: list[str] = Field(description="catalogue features added to the table, in order")
    sort: str | None = Field(description="a column id, '-' prefix descending (null: default)")
    decisions: list[str] = Field(description="decisions shown (empty: the page's default)")
    names: list[str] = Field(description="the user's named views of this table, sorted")
    narrow_columns: list[str] = Field(
        description="table column ids added back on a narrow (phone) table"
    )
    filters: str = Field(description="the filter bar's `f` string ('' : no filters)")


class ViewNames(Schema):
    names: list[str] = Field(description="the user's named views of this table, sorted")
