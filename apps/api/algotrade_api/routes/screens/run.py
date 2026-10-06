"""``POST /screens/{id}/run`` and ``GET /screens/{id}/run/{job_id}``: run a screener on request
(ADR 0033). The run is the nightly's ``screen`` job for the latest session with data, started
only when this screener version has no stored results for it; the request answers at once
(``ready``, or the job's state) and the page polls the job, which only its owner or an admin may
read (ADR 0040)."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query, Response

from algotrade.config.site.users import Role
from algotrade.config.user import UserContext
from algotrade.services.ondemand.screens import READY, RunRequest
from algotrade_api.deps import Caller, OnDemand, User

router = APIRouter(prefix="/screens", tags=["screens"])


@router.post("/{config_id}/run")
def run(
    runner: OnDemand,
    response: Response,
    config_id: str,
    user: User,
    on: Annotated[
        date | None, Query(alias="date", description="default: the latest session with data")
    ] = None,
) -> RunRequest:
    request = runner.request(config_id, UserContext(user), on)
    response.status_code = 200 if request.state in (READY, "complete", "partial") else 202
    return request


@router.get("/{config_id}/run/{job_id}")
def run_status(runner: OnDemand, caller: Caller, config_id: str, job_id: str) -> RunRequest:
    """403 for another user's job unless the caller is an admin (the job's owner is its user)."""
    viewer = UserContext(caller.user_id)
    return runner.status(config_id, job_id, viewer, admin=caller.role is Role.ADMIN)
