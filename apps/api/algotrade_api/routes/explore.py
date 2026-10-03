"""``/explore``: the Explore page's ticker table (any catalogue columns, filtered, sorted,
paged) and multi-ticker compare (features side by side, rebased prices)."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query

from algotrade.services.explore import instruments, universe
from algotrade_api.deps import Filters, Store, name_list
from algotrade_api.routes.instruments import Adjustment
from algotrade_api.schemas.explore import FeatureComparison, PriceComparison, TickerTable

router = APIRouter(prefix="/explore", tags=["explore"])

Session = Annotated[date | None, Query(alias="date", description="default: the latest")]
Ids = Annotated[str, Query(description="comma-separated instrument ids or tickers (max 10)")]


@router.get("/tickers")
def tickers(
    store: Store,
    filters: Filters,
    on: Session = None,
    columns: Annotated[str | None, Query(description="comma-separated feature names")] = None,
    sort: Annotated[str | None, Query(description="a column; '-' prefix: descending")] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=1000)] = 100,
) -> TickerTable:
    table = universe.ticker_table(store, on, filters, name_list(columns), sort, page, size)
    return TickerTable.model_validate(table)


@router.get("/compare")
def compare(
    store: Store,
    ids: Ids,
    features: Annotated[str | None, Query(description="default: the whole catalogue")] = None,
    on: Session = None,
) -> FeatureComparison:
    found = instruments.compare_features(store, name_list(ids), name_list(features) or None, on)
    return FeatureComparison.model_validate(found)


@router.get("/compare/prices")
def compare_prices(
    store: Store,
    ids: Ids,
    start: Annotated[date | None, Query(alias="from")] = None,
    to: date | None = None,
    rebase: Annotated[float, Query(ge=0, description="0: raw closes")] = 100.0,
    adjust: Adjustment = Adjustment.splits,
) -> PriceComparison:
    found = instruments.compare_prices(
        store, name_list(ids), start, to, rebase or None, adjust.value
    )
    return PriceComparison.model_validate(found)
