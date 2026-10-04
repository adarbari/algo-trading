"""``/screens``: screener configs and a screen's results; ``/ideas``: the best tickers over them."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query

from algotrade.services.explore import screens
from algotrade.services.explore.ideas.ranking import ideas_for
from algotrade_api.deps import Store
from algotrade_api.schemas.screens import Ideas, ScreenConfig, ScreenResults

router = APIRouter(prefix="/screens", tags=["screens"])
ideas_router = APIRouter(prefix="/ideas", tags=["ideas"])


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


@ideas_router.get("")
def top(
    store: Store,
    on: Annotated[date | None, Query(alias="date", description="default: the latest")] = None,
    user: Annotated[
        str | None, Query(description="default: the API's user (a label until auth)")
    ] = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 50,
) -> Ideas:
    return Ideas.model_validate(ideas_for(store, on, user, limit))
