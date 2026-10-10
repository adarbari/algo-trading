"""Run an edge evaluation on request (ADR 0059): the owner's ``evaluate-edges`` for one edge,
started from the web app.

Narrow like the on-request screens (ADR 0033): a local runner whose only kind is ``edge-eval``
(the same job the CLI submits, so the rows land in ``results/edge_eval`` and a run record exactly
as the CLI's do), on its own single worker so a 30 to 40 minute evaluation never holds a screen
run behind it. It does not wait for ingestion (the harness reads committed data and publishes
atomically, ADR 0022) and writes only result tables and run records, never market or feature data
(ADR 0005).

Whose run it is (ADR 0059, amended 2026-10-10): the edge's owner's, and only the owner starts it.
A user runs the edges they own (their own, a clone of a site edge included; rows keyed by their
``user_id``, under their split, so an evaluation under any split but the edge's frozen one is
EXPLORATORY); a site edge is the site's, run by an admin as the site (``as_site``, "Run as site"):
a trader, or an admin running it as himself, is refused (``PermissionDeniedError``). The run is
recorded under its owner with ``trigger = ui``. A run is heavy on the owner's Mac, so one
evaluation at a time per owner, across processes: the check and the submit are one step under the
store's lock ``edge-eval:<owner>`` (``claim_edge_eval``: the same claim the CLI and the nightly
take, so a second API process, the CLI or the nightly see it too); a request while another of that
owner's evaluations is queued or running is refused
(``ConflictError``, 409). A job left running by a stopped process is failed on start, and
one older than ``STALE`` no longer counts as in flight.

The decision sessions are the stored outcome sessions (the CLI's default); the outcomes are those
known now; the split is the edge's own ``frozen_from``.
"""

from dataclasses import dataclass, field

from algotrade.config.edges.loading import load_edges
from algotrade.config.user import SITE_USER, UserContext
from algotrade.core.model.errors import ConfigurationError, PermissionDeniedError
from algotrade.data import StoreReader
from algotrade.services.authoring.scope import ConflictError
from algotrade.services.evaluation.cross_section.harness import stored_outcome_sessions
from algotrade.services.jobs.api import open_runner
from algotrade.services.jobs.exclusive import (
    EDGE_EVAL,
    EDGE_EVAL_STALE,
    EdgeEvalBusyError,
    claim_edge_eval,
)
from algotrade.services.jobs.handlers import LIBRARY_HANDLERS
from algotrade.services.jobs.models import JobRecord, JobStatus
from algotrade.services.jobs.runner import LocalJobRunner
from algotrade.services.read.availability.cause import ADMIN_CAUSE, GENERIC
from algotrade.services.read.session import NotFoundError
from algotrade.storage.configs.store import ConfigStore
from algotrade.storage.factory import open_backend
from algotrade.storage.tables.interfaces import Backend
from algotrade.storage.tables.result_writer import ResultWriter

KIND = EDGE_EVAL
TRIGGER = "ui"  # what the run record says started it (nightly | ui | cli)
STORED = (JobStatus.COMPLETE, JobStatus.PARTIAL)  # a job that stored results
STALE = EDGE_EVAL_STALE


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
        self._backend = backend
        self._configs = configs
        self._reader = StoreReader(backend)
        self._writer = ResultWriter(backend)
        resources = {"reader": self._reader, "writer": self._writer, "configs": configs}
        self._jobs = open_runner(
            self._writer.runs_backend, {KIND: LIBRARY_HANDLERS[KIND]}, resources, workers=1
        )
        self._jobs.recover(STALE, (KIND,))

    def request(
        self, edge_id: str, user: UserContext, *, as_site: bool = False, admin: bool = False
    ) -> EvaluationRequest:
        """Start an evaluation of ``edge_id`` for its owner: ``user``, or with ``as_site`` the
        site (admins only).

        ``NotFoundError`` for an edge the caller does not see, ``PermissionDeniedError`` for an
        edge they do not own (a site edge outside ``as_site``) or ``as_site`` by a non-admin,
        ``ConflictError`` while another of the owner's evaluations is queued or running,
        ``ConfigurationError`` when no outcomes are stored."""
        if as_site and not admin:
            raise PermissionDeniedError("only an admin can run an evaluation as the site")
        owner = UserContext(SITE_USER) if as_site else user
        edge = next((e for e in load_edges(self._configs, owner.user_id) if e.id == edge_id), None)
        if edge is None:
            raise NotFoundError(f"unknown edge {edge_id!r}")
        if edge.owner != owner.user_id:
            raise PermissionDeniedError(
                f"edge {edge_id!r} is not yours to run: only its owner can "
                "(an admin runs a site edge with Run as site)"
            )
        stored = stored_outcome_sessions(self._reader)
        if not stored:
            raise ConfigurationError("no outcomes are stored yet: nothing to evaluate")
        params = {
            "edge": edge_id,
            "start": stored[0].isoformat(),
            "end": stored[-1].isoformat(),
            "trigger": TRIGGER,
        }
        try:
            with claim_edge_eval(
                self._backend, owner.user_id, lambda: self._jobs.recover(STALE, (KIND,))
            ):
                job_id = self._jobs.submit(KIND, params, owner, force=True)
        except EdgeEvalBusyError as busy:
            raise ConflictError(str(busy)) from busy
        return self._view(self._jobs.status(job_id))

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

    @property
    def jobs(self) -> LocalJobRunner:
        """The runner whose records ``read_job`` (``status.py``) serves."""
        return self._jobs

    def close(self) -> None:
        self._jobs.shutdown()


def open_ondemand_edges(data_url: str, configs: ConfigStore) -> OnDemandEdges:
    """The on-request evaluator over the store at ``data_url`` (its own backend handle)."""
    return OnDemandEdges(open_backend(data_url), configs)
