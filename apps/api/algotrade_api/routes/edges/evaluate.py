"""``POST /edges/{id}/evaluate``: run an edge evaluation
on request (ADR 0059). The run is the owner's ``edge-eval`` job under the caller's own split (rows
keyed by their user id; EXPLORATORY unless the split is the edge's frozen one); an admin may run
it as the site (``as_site``). One evaluation at a time per user (409 while another runs). The
request answers at once with the job, which the page polls at ``GET /jobs/{job_id}`` (ADR 0037,
amended)."""

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
