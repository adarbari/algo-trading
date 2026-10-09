"""``GET /jobs/{job_id}``: the state of one on-request job (a screen run, an edge evaluation)."""

from datetime import date

from pydantic import Field

from algotrade.services.read.availability.cause import ADMIN_CAUSE, GENERIC
from algotrade_api.schemas.health import Schema


class JobStatus(Schema):
    job_id: str
    kind: str = Field(description="screen or edge-eval")
    state: str = Field(description="queued, running, complete, partial or failed")
    user: str = Field(description="whose job: the caller, or the site")
    session: date | None = Field(description="the session a screen run is for")
    run_id: str | None = Field(description="the stored run (complete or partial)")
    exploratory: bool | None = Field(description="an evaluation's verdict, once it finished")
    error: str | None = Field(
        description="why it failed (admins only: anyone else is told it failed)",
        json_schema_extra={ADMIN_CAUSE: GENERIC},
    )
