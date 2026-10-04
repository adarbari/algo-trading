"""``GET /preferences/screeners/{id}/view``: a user's saved view of a screener's results
(the write is ``PUT`` on the same path, under ``authoring/``)."""

from typing import Annotated

from fastapi import APIRouter, Query

from algotrade.services.explore.screens.view import screener_view
from algotrade_api.deps import Store
from algotrade_api.schemas.screens.view import ScreenerView

router = APIRouter(prefix="/preferences", tags=["screens"])


@router.get("/screeners/{screener_id}/view")
def view(
    store: Store,
    screener_id: str,
    user: Annotated[
        str | None, Query(description="default: the API's user (a label until auth)")
    ] = None,
) -> ScreenerView:
    return ScreenerView.model_validate(screener_view(store, user, screener_id))
