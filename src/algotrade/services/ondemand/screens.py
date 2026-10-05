"""Run a screener on request (ADR 0033): for the latest session with data, unless this screener
version has already run for it.

The API's one result-writing path, narrow like the live recorder's (ADR 0028): a local job
runner whose only kind is ``screen`` (the same job the nightly submits, so a run stores
``results/rule_screen*`` and a run record exactly as the nightly does and everything that reads
them sees it), each run holding the store's ingest lock so it never interleaves with an
ingestion run (it waits for one, its job ``queued`` or ``running`` meanwhile). Nothing here
writes market or feature data (ADR 0005).

A request resolves the screener for the user (their own finalised screen, else a site preset),
picks the session (``on``, else the latest with bars), and answers ``ready`` at once when a run
of this config hash for that session is stored (COMPLETE or PARTIAL); otherwise it submits the
job (the same work already in flight is the same job) and answers its state.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from typing import Any

from algotrade.config.user import SITE_USER, UserContext
from algotrade.core.model.errors import AlgoTradeError, ConfigurationError
from algotrade.data import StoreReader
from algotrade.services.configs import config_ids, resolve_config
from algotrade.services.explore.store import NotFoundError, latest_session
from algotrade.services.jobs.api import open_runner
from algotrade.services.jobs.exclusive import INGEST_LOCK, exclusive_run
from algotrade.services.jobs.handlers import LIBRARY_HANDLERS
from algotrade.services.jobs.models import JobRecord, JobStatus
from algotrade.services.jobs.runner import JobContext, JobKind
from algotrade.services.screening.run import run_job_name
from algotrade.storage.configs.store import ConfigStore
from algotrade.storage.factory import open_backend
from algotrade.storage.runs import RunRecord
from algotrade.storage.tables.interfaces import Backend
from algotrade.storage.tables.result_writer import ResultWriter

KIND = "screen"
READY = "ready"  # results for this version and session are already stored
STORED = (JobStatus.COMPLETE, JobStatus.PARTIAL)


@dataclass(frozen=True)
class RunRequest:
    state: str  # ready, queued, running, complete, partial or failed
    config_id: str
    session: date
    job_id: str | None  # None when the results were already stored
    run_id: str | None  # the stored run (when ready, complete or partial)
    error: str | None  # why a failed run failed


def _locked(kind: JobKind, backend: Backend) -> JobKind:
    """``kind`` holding the store's writer lock while it runs (waiting for an ingestion run)."""

    def handler(params: Mapping[str, Any], context: JobContext) -> Mapping[str, Any]:
        with exclusive_run(backend, INGEST_LOCK, wait=True):
            return kind.handler(params, context)

    return JobKind(handler, kind.identity)


class OnDemandScreens:
    """Requests and tracks screen runs over one store (``backend``) and its configs."""

    def __init__(self, backend: Backend, configs: ConfigStore, workers: int = 1) -> None:
        self._configs = configs
        self._reader = StoreReader(backend)
        self._runs = ResultWriter(backend)
        resources = {"reader": self._reader, "writer": self._runs, "configs": configs}
        handlers = {KIND: _locked(LIBRARY_HANDLERS[KIND], backend)}
        self._jobs = open_runner(self._runs.runs_backend, handlers, resources, workers)

    def _owner(self, config_id: str, user: UserContext) -> UserContext:
        """Whose run it is: the user's own screener, else the site preset (a shared run)."""
        mine = config_id in config_ids(self._configs, user.user_id)
        return user if mine else UserContext(SITE_USER)

    def _stored(
        self, config_id: str, owner: UserContext, config_hash: str, session: date
    ) -> RunRecord | None:
        """The stored run of this config version for ``session`` (None: not run yet)."""
        found = [
            r
            for r in self._runs.runs_for(run_job_name(config_id, owner.user_id), session)
            if r.status in STORED and r.stats.get("config_hash") == config_hash
        ]
        return found[-1] if found else None

    def request(self, config_id: str, user: UserContext, on: date | None = None) -> RunRequest:
        """Run ``config_id`` for the latest session with data (or ``on``) unless it has run."""
        try:
            config = resolve_config(self._configs, config_id, user)
        except ConfigurationError as exc:
            if "unknown config" in str(exc):
                raise NotFoundError(str(exc)) from exc
            raise
        if config.config.kind != "screener":
            raise NotFoundError(f"{config_id} is a {config.config.kind}, not a screener")
        session = on or latest_session(self._reader)
        if session is None:
            raise NotFoundError("no data is stored yet: nothing to screen")
        owner = self._owner(config_id, user)
        config = resolve_config(self._configs, config_id, owner)
        stored = self._stored(config_id, owner, config.hash, session)
        if stored is not None:
            return RunRequest(READY, config_id, session, None, stored.run_id, None)
        params = {"config": config_id, "session": session.isoformat(), "export_dir": None}
        job_id = self._jobs.submit(KIND, params, owner)
        return self._view(config_id, session, self._jobs.status(job_id))

    def status(self, config_id: str, job_id: str) -> RunRequest:
        """The state of a requested run (``NotFoundError`` for a job that is not a screen of it)."""
        try:
            job = self._jobs.status(job_id)
        except AlgoTradeError as exc:
            raise NotFoundError(str(exc)) from exc
        if job.kind != KIND or job.params.get("config") != config_id:
            raise NotFoundError(f"{job_id} is not a run of {config_id}")
        return self._view(config_id, date.fromisoformat(job.params["session"]), job)

    @staticmethod
    def _view(config_id: str, session: date, job: JobRecord) -> RunRequest:
        run_id = job.result.get("run_id") if job.status in STORED else None
        return RunRequest(job.status.value, config_id, session, job.job_id, run_id, job.error)

    def close(self) -> None:
        self._jobs.shutdown()


def open_ondemand(data_url: str, configs: ConfigStore) -> OnDemandScreens:
    """The on-request runner over the store at ``data_url`` (its own backend handle: a file
    store's lock and publishes are shared across processes)."""
    return OnDemandScreens(open_backend(data_url), configs)
