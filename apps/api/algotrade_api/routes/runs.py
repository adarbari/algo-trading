"""``/admin/runs`` (Admin only): recent nightly runs, one run record (items summarised,
failures grouped) and its items."""

from typing import Annotated

from fastapi import APIRouter, Query

from algotrade.services.explore import runs
from algotrade_api.deps import Store
from algotrade_api.schemas.runs import NightlyRun, RunDetail, RunItem

router = APIRouter(prefix="/admin/runs", tags=["admin"])


@router.get("/nightly")
def nightly(store: Store, limit: Annotated[int, Query(ge=1, le=100)] = 10) -> list[NightlyRun]:
    return [NightlyRun.model_validate(r) for r in runs.nightly_runs(store, limit)]


@router.get("/{run_id}")
def run(store: Store, run_id: str) -> RunDetail:
    return RunDetail.model_validate(runs.run_detail(store, run_id))


@router.get("/{run_id}/items")
def run_items(store: Store, run_id: str) -> list[RunItem]:
    return [RunItem.model_validate(i) for i in runs.run_items(store, run_id)]
