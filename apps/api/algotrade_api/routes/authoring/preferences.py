"""``PUT /preferences/ideas`` and ``PUT /preferences/screeners/{id}/view``: save the user's
screener priority and their view of a screener's results (checked before saving)."""

from fastapi import APIRouter

from algotrade.services.authoring import preferences
from algotrade_api.deps import User, Writer
from algotrade_api.schemas.authoring.preferences import (
    IdeasPriority,
    IdeasPriorityBody,
    ScreenerViewBody,
)
from algotrade_api.schemas.screens.view import ScreenerView

router = APIRouter(prefix="/preferences", tags=["ideas"])


@router.put("/ideas")
def save_ideas_priority(writer: Writer, user: User, body: IdeasPriorityBody) -> IdeasPriority:
    saved = preferences.save_ideas_priority(writer, user, body.priority)
    return IdeasPriority(priority=saved)


@router.put("/screeners/{screener_id}/view")
def save_screener_view(
    writer: Writer, user: User, screener_id: str, body: ScreenerViewBody
) -> ScreenerView:
    saved = preferences.save_screener_view(
        writer, user, screener_id, body.columns, body.sort, body.decisions
    )
    return ScreenerView(
        screener_id=screener_id,
        saved=True,
        columns=saved["columns"],
        sort=saved.get("sort"),
        decisions=saved["decisions"],
    )
