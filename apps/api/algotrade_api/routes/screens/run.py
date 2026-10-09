"""``POST /screens/{id}/run``: run a screener on request (ADR 0033). The run is the nightly's
``screen`` job for the latest session with data, started only when this screener version has no
stored results for it; the request answers at once (``ready``, or the job's state) and the page
polls ``GET /jobs/{job_id}`` (ADR 0037, amended)."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query, Response

from algotrade.config.user import UserContext
from algotrade.services.ondemand.screens import READY, RunRequest
from algotrade_api.deps import Caller, OnDemand, User
from algotrade_api.redact import redact

router = APIRouter(prefix="/screens", tags=["screens"])


@router.post("/{config_id}/run")
def run(
    runner: OnDemand,
    caller: Caller,
    response: Response,
    config_id: str,
    user: User,
    on: Annotated[
        date | None, Query(alias="date", description="default: the latest session with data")
    ] = None,
) -> RunRequest:
    request = runner.request(config_id, UserContext(user), on)
    response.status_code = 200 if request.state in (READY, "complete", "partial") else 202
    return redact(request, caller.role)
