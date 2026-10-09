"""``POST /edges/{id}/evaluate`` and ``GET /edges/{id}/evaluate/{job_id}``: run an edge evaluation
on request (ADR 0059). The run is the owner's ``edge-eval`` job under the caller's own split (rows
keyed by their user id; EXPLORATORY unless the split is the edge's frozen one); an admin may run
it as the site (``as_site``). One evaluation at a time per user (409 while another runs). The
request answers at once with the job, which the page polls; only its owner or an admin may read
it (ADR 0040)."""

from typing import Annotated

from fastapi import APIRouter, Query, Response

from algotrade.config.site.users import Role
from algotrade.config.user import UserContext
from algotrade.services.ondemand.edges import EvaluationRequest
from algotrade_api.deps import Caller, OnDemandEvaluations, User
from algotrade_api.redact import redact

router = APIRouter(prefix="/edges", tags=["edges"])


@router.post("/{edge_id}/evaluate")
def evaluate(
    runner: OnDemandEvaluations,
    caller: Caller,
    response: Response,
    edge_id: str,
    user: User,
    as_site: Annotated[
        bool, Query(description="run it for the site, not for you (admins only)")
    ] = False,
) -> EvaluationRequest:
    started = runner.request(
        edge_id, UserContext(user), as_site=as_site, admin=caller.role is Role.ADMIN
    )
    response.status_code = 202
    return redact(started, caller.role)


@router.get("/{edge_id}/evaluate/{job_id}")
def evaluate_status(
    runner: OnDemandEvaluations, caller: Caller, edge_id: str, job_id: str
) -> EvaluationRequest:
    """403 for another user's job unless the caller is an admin (the job's owner is its user)."""
    found = runner.status(
        edge_id, job_id, UserContext(caller.user_id), admin=caller.role is Role.ADMIN
    )
    return redact(found, caller.role)
