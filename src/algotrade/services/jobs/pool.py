"""Parallel work inside one job: a bounded thread pool yielding results as they finish.

Tasks that fan out (one request per underlying) use ``as_completed`` instead of building
their own executor (ADR 0019, ``job-execution``).
"""

import concurrent.futures as cf
from collections.abc import Callable, Iterable, Iterator


def as_completed[T, R](
    fn: Callable[[T], R], items: Iterable[T], workers: int
) -> Iterator[tuple[T, Callable[[], R]]]:
    """Run ``fn`` over ``items`` on ``workers`` threads; yield ``(item, outcome)`` in
    completion order, where ``outcome()`` returns ``fn``'s result or raises its exception."""
    with cf.ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = {pool.submit(fn, item): item for item in items}
        for future in cf.as_completed(futures):
            yield futures[future], future.result
