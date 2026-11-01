"""``PUT`` / ``DELETE /preferences/views/{scope}/view``: save the user's views of a table
(``scope``: ``screener:<id>`` for a screener's results), checked before saving. Reading a view is
GraphQL (``Query.view``). ``PUT /preferences/appearance``: save the user's theme (light, dark or
system; ADR 0085), read back by ``Query.appearance``. The Ideas screener priority is retired
(owner decision 2026-10-22: the Ideas rule ranks by position and weight)."""

from typing import Annotated

from fastapi import APIRouter, Query

from algotrade.services.authoring import preferences
from algotrade_api.deps import User, Writer
from algotrade_api.schemas.authoring.preferences import (
    Appearance,
    AppearanceBody,
    TableView,
    TableViewBody,
    ViewNames,
)

router = APIRouter(prefix="/preferences", tags=["ideas"])


ViewName = Annotated[
    str | None, Query(description="a named view (default: the table's default view)")
]


@router.put("/views/{scope}/view")
def save_view(
    writer: Writer, user: User, scope: str, body: TableViewBody, name: ViewName = None
) -> TableView:
    saved, names = preferences.save_view(
        writer,
        user,
        scope,
        body.columns,
        body.sort,
        body.decisions,
        name,
        body.narrow_columns,
        body.filters,
    )
    return TableView(
        scope=scope,
        name=name,
        saved=True,
        columns=saved["columns"],
        sort=saved.get("sort"),
        decisions=saved["decisions"],
        names=names,
        narrow_columns=saved["narrow_columns"],
        filters=saved.get("filters", ""),
    )


@router.delete("/views/{scope}/view")
def delete_view(
    writer: Writer,
    user: User,
    scope: str,
    name: Annotated[str, Query(description="the named view to remove")],
) -> ViewNames:
    return ViewNames(names=preferences.delete_view(writer, user, scope, name))


@router.put("/appearance")
def save_appearance(writer: Writer, user: User, body: AppearanceBody) -> Appearance:
    return Appearance(theme=preferences.save_appearance(writer, user, body.theme))
