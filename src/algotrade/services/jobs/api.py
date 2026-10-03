"""The service API apps use to run jobs: build a runner, run one job to completion, shut down.

Apps (CLIs) never construct a runner themselves (ADR 0019, R5): they call ``run_job``.
"""

from collections.abc import Mapping, Sequence
from datetime import timedelta
from typing import Any

from algotrade.config.user import UserContext
from algotrade.services.jobs.models import JobRecord
from algotrade.services.jobs.runner import JobHandler, JobKind, LocalJobRunner
from algotrade.storage.interfaces import RunStore


def run_job(
    runs: RunStore,
    handlers: Mapping[str, JobKind | JobHandler],
    resources: Mapping[str, Any],
    kind: str,
    params: Mapping[str, Any],
    user: UserContext,
    *,
    force: bool = True,
    recover: Sequence[str] = (),
) -> JobRecord:
    """Run one job to completion (an explicit run: ``force`` re-runs finished work).

    ``recover``: job kinds the caller is sure no other process is running (it holds their
    lock); any left queued or running is marked failed first, so it cannot block this run.
    """
    runner = LocalJobRunner(runs, handlers, resources)
    if recover:
        runner.recover(timedelta(0), recover)
    try:
        return runner.wait(runner.submit(kind, params, user, force=force))
    finally:
        runner.shutdown()
