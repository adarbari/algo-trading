"""``POST /screeners/{screener_id}/draft-from-text``: the sentence as ``screener_id``'s draft
over the caller's catalogue (the document, what was dropped and why, the model's notes). An
empty or over-long sentence: 400; the model off or not answering: 503."""

from fastapi import APIRouter

from algotrade.services.drafting import screens
from algotrade_api.deps import Context, TextModelDep
from algotrade_api.schemas.drafting.screeners import DraftFromTextBody, ScreenDraft

router = APIRouter(prefix="/screeners", tags=["screeners"])


@router.post("/{screener_id}/draft-from-text")
def draft_from_text(
    ctx: Context, model: TextModelDep, screener_id: str, body: DraftFromTextBody
) -> ScreenDraft:
    result = screens.draft_screen(ctx, model, screener_id, body.text, body.document)
    return ScreenDraft.model_validate(result)
