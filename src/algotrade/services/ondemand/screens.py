"""Run a screener on request (ADR 0033): for the latest session with data, unless this screener
version has already run for it.

The API's one result-writing path, narrow like the live recorder's (ADR 0028): a local job
runner whose only kind is ``screen`` (the same job the nightly submits, so a run stores
``results/rule_screen*`` and a run record exactly as the nightly does and everything that reads
them sees it). It does not wait for an ingestion run: a screen reads only committed data and
publishes its results atomically (ADR 0022, under the store's commit lock), so it cannot
interleave with an ingestion run, and a backfill that holds the ingest lock for hours must not
hold a request for as long. Nothing here writes market or feature data (ADR 0005). Jobs left
queued or running by a stopped API process are marked failed on the next start, so a request
for the same work runs again instead of waiting on a job that is gone.

A request resolves the screener for the user (their own finalised screen, else a site preset),
picks the session (``on``, else the latest with bars), and answers ``ready`` at once when a
COMPLETE run of this config hash for that session is stored; otherwise it submits the job (the
same work already in flight is the same job) and answers its state. A stored PARTIAL run is run
again: it read a table that had no rows for the session, which may have landed since (a rollup
backfilled after the screen ran rejected every row as missing data, 2026-10-07).
"""

from dataclasses import dataclass
from datetime import date, timedelta

from algotrade.config.user import SITE_USER, UserContext
from algotrade.core.model.errors import AlgoTradeError, ConfigurationError, PermissionDeniedError
from algotrade.data import StoreReader
from algotrade.services.configs import config_ids, resolve_config
from algotrade.services.jobs.api import open_runner
from algotrade.services.jobs.handlers import LIBRARY_HANDLERS
from algotrade.services.jobs.models import JobRecord, JobStatus
from algotrade.services.read.session import NotFoundError, latest_session
from algotrade.services.screening.run import run_job_name
from algotrade.storage.configs.store import ConfigStore
from algotrade.storage.factory import open_backend
from algotrade.storage.runs import RunRecord
from algotrade.storage.tables.interfaces import Backend
from algotrade.storage.tables.result_writer import ResultWriter

KIND = "screen"
READY = "ready"  # complete results for this version and session are already stored
STORED = (JobStatus.COMPLETE, JobStatus.PARTIAL)  # a job that stored results
STALE = timedelta(minutes=30)  # a screen takes minutes: older, still "running", is a dead job


@dataclass(frozen=True)
class RunRequest:
    state: str  # ready, queued, running, complete, partial or failed
    config_id: str
    session: date
    job_id: str | None  # None when the results were already stored
    run_id: str | None  # the stored run (when ready, complete or partial)
    error: str | None  # why a failed run failed


class OnDemandScreens:
    """Requests and tracks screen runs over one store (``backend``) and its configs."""

    def __init__(self, backend: Backend, configs: ConfigStore, workers: int = 1) -> None:
        self._configs = configs
        self._reader = StoreReader(backend)
        self._runs = ResultWriter(backend)
        resources = {"reader": self._reader, "writer": self._runs, "configs": configs}
        handlers = {KIND: LIBRARY_HANDLERS[KIND]}
        self._jobs = open_runner(self._runs.runs_backend, handlers, resources, workers)
        self._jobs.recover(STALE, (KIND,))

    def _owner(self, config_id: str, user: UserContext) -> UserContext:
        """Whose run it is: the user's own screener, else the site preset (a shared run)."""
        mine = config_id in config_ids(self._configs, user.user_id)
        return user if mine else UserContext(SITE_USER)

    def _stored(
        self, config_id: str, owner: UserContext, config_hash: str, session: date
    ) -> RunRecord | None:
        """The latest stored run of this config version for ``session`` (None: not run yet)."""
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
        if stored is not None and stored.status == JobStatus.COMPLETE:
            return RunRequest(READY, config_id, session, None, stored.run_id, None)
        params = {"config": config_id, "session": session.isoformat(), "export_dir": None}
        # a PARTIAL run is the same job identity: force it to run again (in flight stays one job)
        job_id = self._jobs.submit(KIND, params, owner, force=stored is not None)
        return self._view(config_id, session, self._jobs.status(job_id))

    def status(
        self, config_id: str, job_id: str, viewer: UserContext, *, admin: bool = False
    ) -> RunRequest:
        """The state of a requested run for ``viewer`` (``NotFoundError`` for a job that is not
        a screen of ``config_id``; ``PermissionDeniedError`` for another user's job unless
        ``admin``: the job is the viewer's own, or the site's shared run of a preset)."""
        try:
            job = self._jobs.status(job_id)
        except AlgoTradeError as exc:
            raise NotFoundError(str(exc)) from exc
        if job.kind != KIND or job.params.get("config") != config_id:
            raise NotFoundError(f"{job_id} is not a run of {config_id}")
        if not (admin or job.user in (viewer.user_id, SITE_USER)):
            raise PermissionDeniedError(f"{job_id} is another user's run")
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
