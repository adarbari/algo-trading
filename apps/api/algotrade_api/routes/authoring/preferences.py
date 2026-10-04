"""``PUT /preferences/ideas``: save the user's screener priority (checked before saving)."""

from fastapi import APIRouter

from algotrade.services.authoring import preferences
from algotrade_api.deps import User, Writer
from algotrade_api.schemas.authoring.preferences import IdeasPriority, IdeasPriorityBody

router = APIRouter(prefix="/preferences", tags=["ideas"])


@router.put("/ideas")
def save_ideas_priority(writer: Writer, user: User, body: IdeasPriorityBody) -> IdeasPriority:
    saved = preferences.save_ideas_priority(writer, user, body.priority)
    return IdeasPriority(priority=saved)
