"""``/admin``: endpoints for the Admin workspace only (role-gating attaches to this prefix):
ingestion completeness per dataset and session, and one cell's drill-down."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query

from algotrade.services.explore import ingestion
from algotrade_api.deps import Store
from algotrade_api.schemas.admin import CellDetail, Completeness

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/ingestion/completeness")
def completeness(store: Store, sessions: Annotated[int, Query(ge=1, le=60)] = 10) -> Completeness:
    return Completeness.model_validate(ingestion.completeness(store, sessions))


@router.get("/ingestion/{dataset:path}/{session}")
def dataset_session(store: Store, dataset: str, session: date) -> CellDetail:
    return CellDetail.model_validate(ingestion.dataset_session(store, dataset, session))
