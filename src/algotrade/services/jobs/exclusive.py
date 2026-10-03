"""One writer at a time: the run lock every writing ingestion command takes (ADR 0019 R5).

Two ingestion runs against the same store (a launchd nightly and a manual backfill, say)
could otherwise resume the same unfinished run or interleave writes to the same tables. The
lock is the store's own (``Backend.lock``: a file lock for the local backend), so it holds
across processes. A second run either fails fast with ``RunLockedError`` or, with
``wait=True``, queues behind the first.
"""

from collections.abc import Iterator
from contextlib import contextmanager

from algotrade.core.model.errors import AlgoTradeError
from algotrade.storage.locks import held
from algotrade.storage.tables.interfaces import Backend

INGEST_LOCK = "ingest"


class RunLockedError(AlgoTradeError):
    """Another run holds the lock (and the caller chose not to wait)."""


@contextmanager
def exclusive_run(backend: Backend, name: str = INGEST_LOCK, wait: bool = False) -> Iterator[None]:
    """Hold the store's ``name`` lock for the block; raise ``RunLockedError`` if it is taken
    and ``wait`` is false."""
    with held(backend.lock(name), wait=wait) as taken:
        if not taken:
            raise RunLockedError(
                f"another {name} run is using this data store; wait for it to finish "
                "or pass --wait to queue behind it"
            )
        yield
