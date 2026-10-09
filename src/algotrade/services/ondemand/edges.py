"""Run an edge evaluation on request (ADR 0059): the owner's ``evaluate-edges`` for one edge,
started from the web app.

Narrow like the on-request screens (ADR 0033): a local runner whose only kind is ``edge-eval``
(the same job the CLI submits, so the rows land in ``results/edge_eval`` and a run record exactly
as the CLI's do), on its own single worker so a 30 to 40 minute evaluation never holds a screen
run behind it. It does not wait for ingestion (the harness reads committed data and publishes
atomically, ADR 0022) and writes only result tables and run records, never market or feature data
(ADR 0005).

Whose run it is: the caller's own (rows keyed by their ``user_id``, under their split, so an
evaluation under any split but the edge's frozen one is EXPLORATORY); a site run (``as_site``)
is an admin's. A run is heavy on the owner's Mac, so one evaluation at a time per user: a request
while another of that user's evaluations is queued or running is refused (``ConflictError``, 409).
The check and the submit are one step under a lock (one API process is assumed, ADR 0028); a job
left running by a stopped process is failed on start, and one older than ``STALE`` no longer
counts as in flight.

The decision sessions are the stored outcome sessions (the CLI's default); the outcomes are those
known now; the split is the user's ``evaluation.toml``, else the edge's ``frozen_from``.
"""

import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from algotrade.config.edges.loading import load_edges
from algotrade.config.user import SITE_USER, UserContext
from algotrade.core.model.errors import AlgoTradeError, ConfigurationError, PermissionDeniedError
from algotrade.data import StoreReader
from algotrade.services.authoring.scope import ConflictError
from algotrade.services.jobs.api import open_runner
from algotrade.services.jobs.handlers import LIBRARY_HANDLERS
from algotrade.services.jobs.models import JobRecord, JobStatus
from algotrade.services.read.availability.cause import ADMIN_CAUSE, GENERIC
from algotrade.services.read.session import NotFoundError
from algotrade.storage.configs.store import ConfigStore
from algotrade.storage.factory import open_backend
from algotrade.storage.tables.interfaces import Backend
from algotrade.storage.tables.result_writer import ResultWriter
from algotrade.storage.tables.schemas import FORWARD_RETURNS

KIND = "edge-eval"
STORED = (JobStatus.COMPLETE, JobStatus.PARTIAL)  # a job that stored results
IN_FLIGHT = (JobStatus.QUEUED, JobStatus.RUNNING)
STALE = timedelta(hours=2)  # the longest evaluation takes ~40 minutes: older, "running", is dead


@dataclass(frozen=True)
class EvaluationRequest:
    state: str  # queued, running, complete, partial or failed
    edge_id: str
    user: str  # whose rows: the caller, or the site
    job_id: str
    run_id: str | None  # the stored harness run (complete or partial)
    exploratory: bool | None  # known once the run finished
    # why a run failed: the error text is for admins, anyone else is told it failed
    error: str | None = field(metadata={ADMIN_CAUSE: GENERIC})


class OnDemandEdges:
    """Requests and tracks edge evaluations over one store (``backend``) and its configs."""

    def __init__(self, backend: Backend, configs: ConfigStore) -> None:
        self._configs = configs
        self._reader = StoreReader(backend)
        self._writer = ResultWriter(backend)
        resources = {"reader": self._reader, "writer": self._writer, "configs": configs}
        self._jobs = open_runner(
            self._writer.runs_backend, {KIND: LIBRARY_HANDLERS[KIND]}, resources, workers=1
        )
        self._jobs.recover(STALE, (KIND,))
        self._guard = threading.Lock()

    def _running(self, user: str) -> JobRecord | None:
        """An evaluation of ``user`` still queued or running (None: free to start one)."""
        now = datetime.now(UTC)
        for run in self._writer.runs_for(f"job:{KIND}"):
            job = JobRecord.from_run(run)
            if job.user == user and job.status in IN_FLIGHT and now - job.submitted_at < STALE:
                return job
        return None

    def request(
        self, edge_id: str, user: UserContext, *, as_site: bool = False, admin: bool = False
    ) -> EvaluationRequest:
        """Start an evaluation of ``edge_id`` for ``user`` (``as_site``: the site's, admins only).

        ``NotFoundError`` for an edge the owner does not see, ``PermissionDeniedError`` for a
        site run by a non-admin, ``ConflictError`` while another of the owner's evaluations is
        queued or running, ``ConfigurationError`` when no outcomes are stored."""
        if as_site and not admin:
            raise PermissionDeniedError("only an admin can run an evaluation as the site")
        owner = UserContext(SITE_USER) if as_site else user
        if edge_id not in {e.id for e in load_edges(self._configs, owner.user_id)}:
            raise NotFoundError(f"unknown edge {edge_id!r}")
        stored = self._reader.dates(FORWARD_RETURNS)
        if not stored:
            raise ConfigurationError("no outcomes are stored yet: nothing to evaluate")
        params = {"edge": edge_id, "start": stored[0].isoformat(), "end": stored[-1].isoformat()}
        with self._guard:
            busy = self._running(owner.user_id)
            if busy is not None:
                raise ConflictError(
                    f"an evaluation of {busy.params.get('edge')} is already running "
                    f"for {owner.user_id}: wait for it to finish"
                )
            job_id = self._jobs.submit(KIND, params, owner, force=True)
        return self._view(self._jobs.status(job_id))

    def status(
        self, edge_id: str, job_id: str, viewer: UserContext, *, admin: bool = False
    ) -> EvaluationRequest:
        """The state of a requested evaluation (``NotFoundError`` for a job that is not an
        evaluation of ``edge_id``; ``PermissionDeniedError`` for another user's unless ``admin``;
        a site run is visible to everyone, like a site preset's)."""
        try:
            job = self._jobs.status(job_id)
        except AlgoTradeError as exc:
            raise NotFoundError(str(exc)) from exc
        if job.kind != KIND or job.params.get("edge") != edge_id:
            raise NotFoundError(f"{job_id} is not an evaluation of {edge_id}")
        if not (admin or job.user in (viewer.user_id, SITE_USER)):
            raise PermissionDeniedError(f"{job_id} is another user's evaluation")
        return self._view(job)

    @staticmethod
    def _view(job: JobRecord) -> EvaluationRequest:
        stored = job.status in STORED
        return EvaluationRequest(
            job.status.value,
            job.params["edge"],
            job.user,
            job.job_id,
            job.result.get("run_id") if stored else None,
            job.result.get("exploratory") if stored else None,
            job.error,
        )

    def close(self) -> None:
        self._jobs.shutdown()


def open_ondemand_edges(data_url: str, configs: ConfigStore) -> OnDemandEdges:
    """The on-request evaluator over the store at ``data_url`` (its own backend handle)."""
    return OnDemandEdges(open_backend(data_url), configs)
