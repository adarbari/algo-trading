"""``PUT /preferences/ideas`` and ``PUT`` / ``DELETE /preferences/views/{scope}/view``: save
the user's screener priority and their views of a table (``scope``: ``screener:<id>`` for a
screener's results), checked before saving. Reading a view is GraphQL (``Query.view``)."""

from typing import Annotated

from fastapi import APIRouter, Query

from algotrade.services.authoring import preferences
from algotrade_api.deps import User, Writer
from algotrade_api.schemas.authoring.preferences import (
    IdeasPriority,
    IdeasPriorityBody,
    TableView,
    TableViewBody,
    ViewNames,
)

router = APIRouter(prefix="/preferences", tags=["ideas"])


@router.put("/ideas")
def save_ideas_priority(writer: Writer, user: User, body: IdeasPriorityBody) -> IdeasPriority:
    saved = preferences.save_ideas_priority(writer, user, body.priority)
    return IdeasPriority(priority=saved)


ViewName = Annotated[
    str | None, Query(description="a named view (default: the table's default view)")
]


@router.put("/views/{scope}/view")
def save_view(
    writer: Writer, user: User, scope: str, body: TableViewBody, name: ViewName = None
) -> TableView:
    saved, names = preferences.save_view(
        writer, user, scope, body.columns, body.sort, body.decisions, name
    )
    return TableView(
        scope=scope,
        name=name,
        saved=True,
        columns=saved["columns"],
        sort=saved.get("sort"),
        decisions=saved["decisions"],
        names=names,
    )


@router.delete("/views/{scope}/view")
def delete_view(
    writer: Writer,
    user: User,
    scope: str,
    name: Annotated[str, Query(description="the named view to remove")],
) -> ViewNames:
    return ViewNames(names=preferences.delete_view(writer, user, scope, name))
