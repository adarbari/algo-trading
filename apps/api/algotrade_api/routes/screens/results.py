"""``/screens``: screener configs and a screen's results."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query

from algotrade.services.explore.screens import results as screens
from algotrade_api.deps import Store
from algotrade_api.schemas.screens.results import ScreenConfig, ScreenResults

router = APIRouter(prefix="/screens", tags=["screens"])


@router.get("")
def screen_configs(store: Store) -> list[ScreenConfig]:
    return [ScreenConfig.model_validate(c) for c in screens.screen_configs(store)]


@router.get("/{config_id}/results")
def results(
    store: Store,
    config_id: str,
    on: Annotated[date | None, Query(alias="date")] = None,
    decision: str | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=1000)] = 100,
) -> ScreenResults:
    found = screens.screen_results(store, config_id, on, decision, page, size)
    return ScreenResults.model_validate(found)
