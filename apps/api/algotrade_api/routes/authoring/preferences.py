"""``PUT`` / ``DELETE /preferences/views/{scope}/view``: save the user's views of a table
(``scope``: ``screener:<id>`` for a screener's results), checked before saving. Reading a view is
GraphQL (``Query.view``). ``PUT /preferences/appearance``: save the user's theme (light, dark or
system; ADR 0085), read back by ``Query.appearance``. ``PUT /preferences/watchlist`` and
``/preferences/ideas``: save the watchlist (instrument ids; 404 on an empty store, which has no
reference to check them against) and the default Ideas tab (ADR 0083), read back by
``Query.traderPreferences``. The Ideas screener priority is retired
(owner decision 2026-10-22: the Ideas rule ranks by position and weight)."""

from typing import Annotated

from fastapi import APIRouter, Query

from algotrade.services.authoring import preferences
from algotrade_api.deps import Context, User, Writer
from algotrade_api.schemas.authoring.preferences import (
    Appearance,
    AppearanceBody,
    Ideas,
    IdeasBody,
    TableView,
    TableViewBody,
    ViewNames,
    Watchlist,
    WatchlistBody,
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


@router.put("/watchlist")
def save_watchlist(writer: Writer, user: User, ctx: Context, body: WatchlistBody) -> Watchlist:
    return Watchlist(instruments=preferences.save_watchlist(writer, user, body.instruments, ctx))


@router.put("/ideas")
def save_ideas(writer: Writer, user: User, body: IdeasBody) -> Ideas:
    return Ideas(default_tab=preferences.save_ideas_tab(writer, user, body.default_tab))
