"""``/screeners/{id}``: read, draft, finalise, copy, rebase and schedule a user's rule screen.
``?user=`` names the user (a label until identity arrives; default ``ALGOTRADE_USER``)."""

from fastapi import APIRouter

from algotrade.services.authoring import presets, screens
from algotrade_api.deps import User, Writer
from algotrade_api.schemas.authoring.screeners import (
    CopyBody,
    Draft,
    DraftBody,
    Finalised,
    Schedule,
    ScheduleBody,
    ScreenerDetail,
    ScreenerListItem,
    ScreenerVersion,
)

router = APIRouter(prefix="/screeners", tags=["screeners"])


@router.get("")
def screeners(writer: Writer, user: User) -> list[ScreenerListItem]:
    """The user's screens: finalised ones and draft-only ones (status DRAFT)."""
    return [ScreenerListItem.model_validate(s) for s in screens.list_screens(writer, user)]


@router.get("/{screener_id}")
def screener(writer: Writer, user: User, screener_id: str) -> ScreenerDetail:
    return ScreenerDetail.model_validate(screens.screen_detail(writer, user, screener_id))


@router.get("/{screener_id}/versions")
def versions(writer: Writer, user: User, screener_id: str) -> list[ScreenerVersion]:
    found = screens.screen_versions(writer, user, screener_id)
    return [ScreenerVersion.model_validate(v) for v in found]


@router.put("/{screener_id}/draft")
def save_draft(writer: Writer, user: User, screener_id: str, body: DraftBody) -> Draft:
    return Draft(
        screener_id=screener_id,
        document=screens.save_draft(writer, user, screener_id, body.document),
    )


@router.delete("/{screener_id}/draft", status_code=204)
def discard_draft(writer: Writer, user: User, screener_id: str) -> None:
    screens.discard_draft(writer, user, screener_id)


@router.post("/{screener_id}/finalise")
def finalise(writer: Writer, user: User, screener_id: str) -> Finalised:
    return Finalised.model_validate(screens.finalise(writer, user, screener_id))


@router.post("/{screener_id}/copy", status_code=201)
def copy(writer: Writer, user: User, screener_id: str, body: CopyBody) -> Draft:
    document = presets.copy_preset(writer, user, screener_id, body.preset)
    return Draft(screener_id=screener_id, document=document)


@router.post("/{screener_id}/rebase")
def rebase(writer: Writer, user: User, screener_id: str) -> Draft:
    return Draft(screener_id=screener_id, document=presets.rebase(writer, user, screener_id))


@router.put("/{screener_id}/schedule")
def schedule(writer: Writer, user: User, screener_id: str, body: ScheduleBody) -> Schedule:
    value = screens.set_schedule(writer, user, screener_id, body.schedule)
    return Schedule(screener_id=screener_id, schedule=value)
