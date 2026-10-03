"""The job runner protocol and a local thread-pool implementation."""

import concurrent.futures as cf
import threading
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from algotrade.config.user import UserContext
from algotrade.core.errors import AlgoTradeError, ConfigurationError
from algotrade.services.jobs.models import JobRecord, JobStatus, job_id_for
from algotrade.storage.interfaces import RunStore


@dataclass(frozen=True)
class JobContext:
    """What a handler gets besides its params. Apps put their readers/writers here.
    ``jobs``: the runner executing this job, so a handler can run child jobs (nightly ->
    ``screen``) through it."""

    user: UserContext
    resources: Mapping[str, Any]
    jobs: "JobRunner | None" = None


# A handler returns a JSON-able summary; a ``"_partial": True`` entry marks a partial result.
type JobHandler = Callable[[Mapping[str, Any], JobContext], Mapping[str, Any]]
# What makes two submissions the same job (default: the params themselves).
type JobIdentity = Callable[[Mapping[str, Any], JobContext], Mapping[str, Any]]


@dataclass(frozen=True)
class JobKind:
    handler: JobHandler
    identity: JobIdentity | None = None


class JobRunner(Protocol):
    def submit(
        self, kind: str, params: Mapping[str, Any], user: UserContext, force: bool = False
    ) -> str: ...

    def status(self, job_id: str) -> JobRecord: ...

    def wait(self, job_id: str, timeout: float | None = None) -> JobRecord: ...

    def run(
        self, kind: str, params: Mapping[str, Any], user: UserContext, force: bool = False
    ) -> JobRecord: ...


class LocalJobRunner:
    """Runs jobs on a small thread pool in this process; records persist in ``runs``."""

    def __init__(
        self,
        runs: RunStore,
        handlers: Mapping[str, JobKind | JobHandler],
        resources: Mapping[str, Any],
        workers: int = 2,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._kinds = {k: v if isinstance(v, JobKind) else JobKind(v) for k, v in handlers.items()}
        self._runs, self._resources = runs, resources
        self._clock = clock
        self._pool = cf.ThreadPoolExecutor(max_workers=workers, thread_name_prefix="job")
        self._futures: dict[str, cf.Future[None]] = {}
        self._lock = threading.Lock()

    @property
    def kinds(self) -> tuple[str, ...]:
        return tuple(sorted(self._kinds))

    def submit(
        self, kind: str, params: Mapping[str, Any], user: UserContext, force: bool = False
    ) -> str:
        """Queue a job. Identical work returns the existing job unless it failed, or unless
        ``force`` asks to run a finished job again (an explicit re-run, e.g. from a CLI)."""
        return self._claim(kind, params, user, force, pooled=True)[0]

    def run(
        self, kind: str, params: Mapping[str, Any], user: UserContext, force: bool = False
    ) -> JobRecord:
        """Run a job to completion in the caller's thread (same identity and records as
        ``submit``). Handlers run child jobs this way, so a busy pool cannot deadlock them."""
        job_id, record = self._claim(kind, params, user, force, pooled=False)
        if record is not None:
            self._execute(record)
            return self.status(job_id)
        return self.wait(job_id)

    def _claim(
        self, kind: str, params: Mapping[str, Any], user: UserContext, force: bool, pooled: bool
    ) -> tuple[str, JobRecord | None]:
        """-> (job id, the new queued record, or ``None`` if the work exists). ``pooled``:
        start it on the pool now (under the lock, so ``recover`` sees it in flight)."""
        if kind not in self._kinds:
            raise ConfigurationError(f"unknown job kind {kind!r}; known: {list(self.kinds)}")
        identity_fn = self._kinds[kind].identity
        context = JobContext(user, self._resources)
        identity = identity_fn(params, context) if identity_fn else params
        job_id = job_id_for(kind, identity, user)
        with self._lock:
            existing = self._runs.load(job_id)
            in_flight = existing is not None and existing.status in (
                JobStatus.QUEUED,
                JobStatus.RUNNING,
            )
            done = existing is not None and existing.status is not JobStatus.FAILED
            if in_flight or (done and not force):
                return job_id, None  # same work already queued, running or done
            record = JobRecord(job_id, kind, dict(params), user.user_id, self._clock())
            self._runs.save(record.to_run())
            if pooled:
                self._futures[job_id] = self._pool.submit(self._execute, record)
        return job_id, record

    def status(self, job_id: str) -> JobRecord:
        run = self._runs.load(job_id)
        if run is None:
            raise AlgoTradeError(f"unknown job {job_id!r}")
        return JobRecord.from_run(run)

    def wait(self, job_id: str, timeout: float | None = None) -> JobRecord:
        future = self._futures.get(job_id)
        if future is not None:
            future.result(timeout=timeout)
        return self.status(job_id)

    def recover(self, stale_after: timedelta, kinds: Sequence[str] | None = None) -> list[str]:
        """Mark jobs left queued/running by a crashed process as failed (re-submit to retry).

        ``kinds`` limits it to the kinds the caller is sure no other process is running (e.g.
        under the ingest run lock, ``stale_after=0`` is safe for the kinds it guards)."""
        now, failed = self._clock(), []
        for kind in self.kinds if kinds is None else [k for k in kinds if k in self._kinds]:
            for run in self._runs.find(f"job:{kind}"):
                record = JobRecord.from_run(run)
                in_flight = record.job_id in self._futures
                if not record.done and not in_flight and now - record.submitted_at > stale_after:
                    record.status, record.finished_at = JobStatus.FAILED, now
                    record.error = "abandoned: the process running it stopped"
                    self._runs.save(record.to_run())
                    failed.append(record.job_id)
        return failed

    def shutdown(self) -> None:
        self._pool.shutdown(wait=True)

    def _execute(self, record: JobRecord) -> None:
        record.status = JobStatus.RUNNING
        self._runs.save(record.to_run())
        context = JobContext(UserContext(record.user), self._resources, self)
        try:
            summary = dict(self._kinds[record.kind].handler(record.params, context))
            partial = summary.pop("_partial", False)
            record.result = summary
            record.status = JobStatus.PARTIAL if partial else JobStatus.COMPLETE
        except Exception as exc:
            record.status, record.error = JobStatus.FAILED, f"{type(exc).__name__}: {exc}"
        record.finished_at = self._clock()
        self._runs.save(record.to_run())
