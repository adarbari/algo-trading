"""``GET /jobs/{job_id}``: the state of one on-request job, whatever started it (ADR 0037,
amended). The caller reads their own jobs, an admin any, a site job is shared; anyone else's is
404, the same as an id that does not exist (ADR 0040)."""

from fastapi import APIRouter

from algotrade.config.site.users import Role
from algotrade.config.user import UserContext
from algotrade.services.ondemand.status import read_job
from algotrade_api.deps import Caller, JobRunner
from algotrade_api.redact import redact
from algotrade_api.schemas.jobs import JobStatus

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("/{job_id}")
def job_status(runner: JobRunner, caller: Caller, job_id: str) -> JobStatus:
    found = read_job(runner, job_id, UserContext(caller.user_id), admin=caller.role is Role.ADMIN)
    return redact(JobStatus.model_validate(found), caller.role)
