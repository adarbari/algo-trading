"""``POST /screeners/preview``: evaluate an unsaved rule-screen draft (an invalid one: 400
naming the field path)."""

from fastapi import APIRouter

from algotrade.services.preview import screens
from algotrade_api.deps import Caller, Context, Store, acting_for
from algotrade_api.schemas.preview.screeners import PreviewBody, ScreenPreview

router = APIRouter(prefix="/screeners", tags=["screeners"])


@router.post("/preview")
def preview(ctx: Context, store: Store, caller: Caller, body: PreviewBody) -> ScreenPreview:
    who = acting_for(caller, body.user)
    result = screens.preview_screen(ctx, store.preview_cache, body.spec, who, body.limit)
    return ScreenPreview.model_validate(result)
