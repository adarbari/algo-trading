"""Job records: the run file name and the record's ``job`` agree for every job kind, so
``find()`` (which skips files by name, ``job_of_name``) never drops a job's records."""

from datetime import UTC, datetime

import pytest

from algotrade.config.user import UserContext
from algotrade.services.jobs.handlers import LIBRARY_HANDLERS
from algotrade.services.jobs.models import JobRecord, job_id_for
from algotrade.storage.runs import is_job_record_name, job_of_name


@pytest.mark.parametrize("kind", sorted(LIBRARY_HANDLERS))
def test_the_name_of_a_job_record_implies_its_job(kind: str) -> None:
    user = UserContext("site")
    job_id = job_id_for(kind, {"a": 1}, user)
    run = JobRecord(job_id, kind, {"a": 1}, "site", datetime(2026, 10, 1, tzinfo=UTC)).to_run()
    assert job_of_name(job_id) == run.job
    assert is_job_record_name(job_id)
