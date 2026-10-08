"""The deploy hold (ADR 0057): run a command only while neither the deploy lock nor the ingest
run lock is taken, so a deploy never runs over an ingest.

``hold`` takes the store's ``deploy`` lock, then its ingest run lock, both without waiting, and
runs the command under them; ``BUSY`` (without running it) if either is taken. The ingestion app
owns the ingest lock, so the hold lives here and ``algotrade-ingest deploy-hold`` is what
``scripts/ops/deploy.sh`` calls. It is not an ingest run: it writes nothing to the store.
"""

from collections.abc import Callable

from algotrade.services.jobs import RunLockedError, exclusive_run
from algotrade.storage.tables.interfaces import Backend

DEPLOY_LOCK = "deploy"
BUSY = 75  # exit code when a lock is taken (EX_TEMPFAIL)


def hold(backend: Backend, run: Callable[[], int]) -> int:
    """Run ``run`` holding the store's deploy lock, then its ingest lock (both non-blocking);
    ``BUSY`` if either is taken (an ingest is writing, or another deploy is under way)."""
    try:
        with exclusive_run(backend, DEPLOY_LOCK, wait=False), exclusive_run(backend, wait=False):
            return run()
    except RunLockedError:
        return BUSY
