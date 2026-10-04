"""``/ideas``: the best tickers over the user's rule screens."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query

from algotrade.services.explore.ideas.ranking import ideas_for
from algotrade_api.deps import Store
from algotrade_api.schemas.screens.ideas import Ideas

router = APIRouter(prefix="/ideas", tags=["ideas"])


@router.get("")
def top(
    store: Store,
    on: Annotated[date | None, Query(alias="date", description="default: the latest")] = None,
    user: Annotated[
        str | None, Query(description="default: the API's user (a label until auth)")
    ] = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 50,
) -> Ideas:
    return Ideas.model_validate(ideas_for(store, on, user, limit))
