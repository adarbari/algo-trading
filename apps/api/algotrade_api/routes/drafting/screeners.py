"""``POST /screeners/{screener_id}/draft-from-text``: the sentence as ``screener_id``'s draft
over the caller's catalogue (the document, what was dropped and why, the model's notes) and the
``draft_session_id`` that ties it to the screen later saved from it. An empty or over-long
sentence: 400; the model off or not answering: 503. The feedback events of the draft are recorded
in the background (ADR 0066) and never fail the request."""

from fastapi import APIRouter

from algotrade.services.drafting import screens
from algotrade.services.drafting.prompt import PROMPT_VERSION
from algotrade_api import feedback
from algotrade_api.deps import Context, Drafts, Feedback, TextModelDep
from algotrade_api.schemas.drafting.screeners import DraftFromTextBody, ScreenDraft

router = APIRouter(prefix="/screeners", tags=["screeners"])


@router.post("/{screener_id}/draft-from-text")
def draft_from_text(
    ctx: Context,
    model: TextModelDep,
    sink: Feedback,
    drafts: Drafts,
    screener_id: str,
    body: DraftFromTextBody,
) -> ScreenDraft:
    user = ctx.user.user_id
    session_id = feedback.record_requested(sink, user, screener_id, body.text)
    result = screens.draft_screen(ctx, model, screener_id, body.text, body.document)
    feedback.record_returned(
        sink, drafts, session_id, user, screener_id, body.text, result.document,
        [{"id": d.id, "field": d.field} for d in result.dropped],
        (result.call_id,) if result.call_id else (), ctx.features,
        PROMPT_VERSION,
    )  # fmt: skip
    return ScreenDraft.model_validate(result).model_copy(update={"draft_session_id": session_id})
