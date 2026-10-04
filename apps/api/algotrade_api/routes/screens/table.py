"""``GET /screens/{id}/table``: a rule screen's latest run as a review table (ADR 0031)."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query

from algotrade.services.explore.screens.table import screen_table
from algotrade_api.deps import Store, name_list
from algotrade_api.schemas.screens.table import ScreenTable

router = APIRouter(prefix="/screens", tags=["screens"])


@router.get("/{config_id}/table")
def table(
    store: Store,
    config_id: str,
    on: Annotated[date | None, Query(alias="date", description="default: the latest")] = None,
    decision: Annotated[
        str | None, Query(description="comma-separated decisions (default: all)")
    ] = None,
    change: Annotated[
        str | None, Query(description="new or dropped since the previous run")
    ] = None,
    q: Annotated[str | None, Query(description="ticker or name contains")] = None,
    columns: Annotated[
        str | None, Query(description="comma-separated catalogue features to add")
    ] = None,
    sort: Annotated[
        str | None,
        Query(
            description="rank, score, symbol, name, decision, criterion:<id>, column:<name> or "
            "a requested feature; '-' prefix: descending; nulls last (default: rank)"
        ),
    ] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=1000)] = 100,
) -> ScreenTable:
    found = screen_table(
        store, config_id, on, name_list(decision), change, q, name_list(columns), sort, page, size
    )
    return ScreenTable.model_validate(found)
