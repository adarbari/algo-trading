"""The deploy hold (ADR 0057): run a command only while the deploy lock (and, unless the deploy
says otherwise, the ingest run lock) is free, so a deploy that touches what an ingest loads
never runs over one.

``hold`` takes the store's ``deploy`` lock, then (``ingest=True``, the default) its ingest run
lock, both without waiting, and runs the command under them; ``BUSY`` (without running it) if
either is taken. ``ingest=False`` (``deploy-hold --deploy-only``) is for a change no running
ingest loads (web, API, docs): it takes the deploy lock alone. The ingestion app
owns the ingest lock, so the hold lives here and ``algotrade-ingest deploy-hold`` is what
``scripts/ops/deploy.sh`` calls. It is not an ingest run: it writes nothing to the store.
"""

from collections.abc import Callable

from algotrade.services.jobs import RunLockedError, exclusive_run
from algotrade.storage.tables.interfaces import Backend

DEPLOY_LOCK = "deploy"
BUSY = 75  # exit code when a lock is taken (EX_TEMPFAIL)


def hold(backend: Backend, run: Callable[[], int], ingest: bool = True) -> int:
    """Run ``run`` holding the store's deploy lock, then (``ingest``) its ingest lock (both
    non-blocking); ``BUSY`` if one is taken (an ingest is writing, or another deploy is under
    way)."""
    try:
        with exclusive_run(backend, DEPLOY_LOCK, wait=False):
            if not ingest:
                return run()
            with exclusive_run(backend, wait=False):
                return run()
    except RunLockedError:
        return BUSY
