"""The status of an on-request job (ADR 0037, amended): one read for every kind of job the API
starts (a screen run, an edge evaluation), whatever started it.

The job record is the ``services/jobs`` runner's; this module only decides who may see it and
shapes it. A caller reads their own jobs, an admin reads any, and a site job (a preset's shared
screen run, a site evaluation) is visible to everyone, like the preset itself. Anyone else's job
is ``NotFoundError`` (404), exactly like an id that does not exist, so an id reveals nothing.
"""

from dataclasses import dataclass, field
from datetime import date

from algotrade.config.user import SITE_USER, UserContext
from algotrade.core.model.errors import AlgoTradeError
from algotrade.services.jobs.models import JobStatus
from algotrade.services.ondemand import edges, screens
from algotrade.services.ondemand.edges import OnDemandEdges
from algotrade.services.ondemand.screens import OnDemandScreens
from algotrade.services.read.availability.cause import ADMIN_CAUSE, GENERIC
from algotrade.services.read.session import NotFoundError

SHARED_KINDS = (screens.KIND, edges.KIND)  # kinds whose site-owned jobs everyone may read
STORED = (JobStatus.COMPLETE, JobStatus.PARTIAL)  # a job that stored results


@dataclass(frozen=True)
class JobView:
    job_id: str
    kind: str  # screen or edge-eval
    state: str  # queued, running, complete, partial or failed
    user: str  # whose job: the caller, or the site
    session: date | None  # the session a screen run is for
    run_id: str | None  # the stored run (complete or partial)
    exploratory: bool | None  # an evaluation's verdict, once it finished
    # why a job failed: the error text is for admins, anyone else is told it failed
    error: str | None = field(metadata={ADMIN_CAUSE: GENERIC})


def read_job(
    source: OnDemandScreens | OnDemandEdges, job_id: str, viewer: UserContext, *, admin: bool
) -> JobView:
    """The state of ``job_id`` for ``viewer`` (``NotFoundError``: unknown, or not theirs). Either
    runner serves any job: both keep their records in the one store."""
    try:
        job = source.jobs.status(job_id)
    except AlgoTradeError as exc:
        raise NotFoundError(f"unknown job {job_id!r}") from exc
    shared = job.user == SITE_USER and job.kind in SHARED_KINDS
    if not (admin or shared or job.user == viewer.user_id):
        raise NotFoundError(f"unknown job {job_id!r}")
    stored = job.status in STORED
    session = job.params.get("session")
    return JobView(
        job.job_id,
        job.kind,
        job.status.value,
        job.user,
        date.fromisoformat(session) if session else None,
        job.result.get("run_id") if stored else None,
        job.result.get("exploratory") if stored else None,
        job.error,
    )
