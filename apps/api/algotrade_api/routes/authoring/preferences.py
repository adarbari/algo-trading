"""``PUT /preferences/ideas`` and ``PUT /preferences/screeners/{id}/view``: save the user's
screener priority and their view of a screener's results (checked before saving)."""

from typing import Annotated

from fastapi import APIRouter, Query

from algotrade.services.authoring import preferences
from algotrade_api.deps import User, Writer
from algotrade_api.schemas.authoring.preferences import (
    IdeasPriority,
    IdeasPriorityBody,
    ScreenerViewBody,
)
from algotrade_api.schemas.screens.view import ScreenerView, ViewNames

router = APIRouter(prefix="/preferences", tags=["ideas"])


@router.put("/ideas")
def save_ideas_priority(writer: Writer, user: User, body: IdeasPriorityBody) -> IdeasPriority:
    saved = preferences.save_ideas_priority(writer, user, body.priority)
    return IdeasPriority(priority=saved)


ViewName = Annotated[
    str | None, Query(description="a named view (default: the screener's default view)")
]


@router.put("/screeners/{screener_id}/view")
def save_screener_view(
    writer: Writer, user: User, screener_id: str, body: ScreenerViewBody, name: ViewName = None
) -> ScreenerView:
    saved, names = preferences.save_screener_view(
        writer, user, screener_id, body.columns, body.sort, body.decisions, name
    )
    return ScreenerView(
        screener_id=screener_id,
        name=name,
        saved=True,
        columns=saved["columns"],
        sort=saved.get("sort"),
        decisions=saved["decisions"],
        names=names,
    )


@router.delete("/screeners/{screener_id}/view")
def delete_screener_view(
    writer: Writer,
    user: User,
    screener_id: str,
    name: Annotated[str, Query(description="the named view to remove")],
) -> ViewNames:
    return ViewNames(names=preferences.delete_screener_view(writer, user, screener_id, name))
