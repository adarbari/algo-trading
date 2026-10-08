"""``TableView``: a user's saved view of a table (``scope``: ``screener:<id>`` for a
screener's results): the catalogue columns they added, the sort and the decisions shown
(``saved`` false: nothing saved)."""

from typing import Self

import strawberry

from algotrade.services.read.screens import views


@strawberry.type(
    description="A user's saved view of a table (`scope`: `screener:<id>`); `saved` false: "
    "nothing saved, the page applies its defaults"
)
class TableView:
    scope: str
    name: str | None
    saved: bool
    columns: list[str]
    sort: str | None
    decisions: list[str]
    names: list[str]
    narrow_columns: list[str]

    @classmethod
    def of(cls, d: views.TableView) -> Self:
        return cls(
            scope=d.scope,
            name=d.name,
            saved=d.saved,
            columns=list(d.columns),
            sort=d.sort,
            decisions=list(d.decisions),
            names=list(d.names),
            narrow_columns=list(d.narrow_columns),
        )
