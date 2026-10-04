"""``POST /screeners/preview``: evaluate an unsaved rule-screen draft (an invalid one: 400
naming the field path)."""

from fastapi import APIRouter

from algotrade.services.explore.preview import screens
from algotrade_api.deps import Store
from algotrade_api.schemas.preview.screeners import PreviewBody, ScreenPreview

router = APIRouter(prefix="/screeners", tags=["screeners"])


@router.post("/preview")
def preview(store: Store, body: PreviewBody) -> ScreenPreview:
    result = screens.preview_screen(store, body.spec, body.user, body.limit)
    return ScreenPreview.model_validate(result)
