"""``/universe`` (filtered, paged) and the Admin review lists ``/admin/review/figi``,
``/admin/review/leveraged``."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query

from algotrade.services.explore import universe
from algotrade_api.deps import Filters, Store
from algotrade_api.schemas.universe import ReviewList, UniversePage

router = APIRouter(tags=["universe"])

Session = Annotated[date | None, Query(alias="date", description="default: the latest")]


@router.get("/universe")
def universe_page(
    store: Store,
    filters: Filters,
    on: Session = None,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=1000)] = 100,
) -> UniversePage:
    return UniversePage.model_validate(universe.universe_page(store, on, filters, page, size))


@router.get("/admin/review/figi", tags=["admin"])
def figi_review(store: Store) -> ReviewList:
    return ReviewList.model_validate(universe.figi_review(store))


@router.get("/admin/review/leveraged", tags=["admin"])
def leverage_review(store: Store, on: Session = None) -> ReviewList:
    return ReviewList.model_validate(universe.leverage_review(store, on))
