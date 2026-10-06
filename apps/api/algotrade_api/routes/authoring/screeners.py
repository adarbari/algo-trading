"""``/screeners/{id}``: draft, finalise, copy, rebase and delete a user's rule screen (a
finalised screen runs nightly, ADR 0033; a deleted one is archived). Reading a screen (its
draft, versions and preset pin) is GraphQL (``Query.myScreens``, ``screenDetail``,
``screenVersions``; ADR 0037).
The write is for the caller; an admin names another user in the ``X-Act-For`` header (ADR 0040)."""

from fastapi import APIRouter

from algotrade.services.authoring import presets, screens
from algotrade_api.deps import User, Writer
from algotrade_api.schemas.authoring.screeners import CopyBody, Draft, DraftBody, Finalised

router = APIRouter(prefix="/screeners", tags=["screeners"])


@router.delete("/{screener_id}", status_code=204)
def delete_screener(writer: Writer, user: User, screener_id: str) -> None:
    """Delete the user's screen: its draft and versions are archived (off the list and the
    nightly; stored runs stay). 404 when the user has no such screen (a site preset is changed
    only by pull request)."""
    screens.delete_screen(writer, user, screener_id)


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
