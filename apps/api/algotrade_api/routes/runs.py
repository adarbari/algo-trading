"""``/admin/runs`` (Admin only): recent nightly runs and one run record (items summarised,
failures grouped)."""

from typing import Annotated

from fastapi import APIRouter, Query

from algotrade.services.explore import runs
from algotrade_api.deps import Store
from algotrade_api.schemas.runs import NightlyRun, RunDetail

router = APIRouter(prefix="/admin/runs", tags=["admin"])


@router.get("/nightly")
def nightly(store: Store, limit: Annotated[int, Query(ge=1, le=100)] = 10) -> list[NightlyRun]:
    return [NightlyRun.model_validate(r) for r in runs.nightly_runs(store, limit)]


@router.get("/{run_id}")
def run(store: Store, run_id: str) -> RunDetail:
    return RunDetail.model_validate(runs.run_detail(store, run_id))
