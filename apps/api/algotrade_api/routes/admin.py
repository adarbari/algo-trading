"""``/admin``: endpoints for the Admin workspace only (role-gating attaches to this prefix):
ingestion completeness per dataset and session, one cell's drill-down, the data-quality checks,
the live verification vs IBKR and the owner's review lists (FIGI, leverage)."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query

from algotrade.services.explore import ingestion, review, runs
from algotrade_api.deps import Store
from algotrade_api.schemas.admin import CellDetail, Completeness, ReviewList, Verification
from algotrade_api.schemas.runs import QualityReport

router = APIRouter(prefix="/admin", tags=["admin"])

Session = Annotated[date | None, Query(alias="date", description="default: the latest")]


@router.get("/ingestion/completeness")
def completeness(store: Store, sessions: Annotated[int, Query(ge=1, le=60)] = 10) -> Completeness:
    return Completeness.model_validate(ingestion.completeness(store, sessions))


@router.get("/ingestion/{dataset:path}/{session}")
def dataset_session(store: Store, dataset: str, session: date) -> CellDetail:
    return CellDetail.model_validate(ingestion.dataset_session(store, dataset, session))


@router.get("/quality")
def quality(store: Store, on: Session = None) -> QualityReport:
    return QualityReport.model_validate(runs.quality_checks(store, on))


@router.get("/verification/ibkr")
def verification(store: Store, on: Session = None) -> Verification:
    return Verification.model_validate(ingestion.verification(store, on))


@router.get("/review/figi")
def figi_review(store: Store) -> ReviewList:
    return ReviewList.model_validate(review.figi_review(store))


@router.get("/review/leveraged")
def leverage_review(store: Store, on: Session = None) -> ReviewList:
    return ReviewList.model_validate(review.leverage_review(store, on))
