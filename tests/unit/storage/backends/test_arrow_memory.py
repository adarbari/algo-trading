"""Arrow's memory knobs: thread caps stick, releasing the pool is safe when idle."""

import pyarrow as pa

from algotrade.storage.backends.arrow_memory import limit_threads, release_unused


def test_limit_threads_sets_both_pools() -> None:
    before = (pa.cpu_count(), pa.io_thread_count())
    try:
        limit_threads(2, 4)
        assert (pa.cpu_count(), pa.io_thread_count()) == (2, 4)
    finally:
        limit_threads(*before)


def test_release_unused_runs_on_an_idle_pool() -> None:
    release_unused()
