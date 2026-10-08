"""Keeps blocking work off the API's event loop (ADR 0037): every read of the graph is parquet
and pandas work, and a resolver that does it on the loop stalls every other request, ``/health``
included (the hosted API took 28-36 s to answer it during a page load).

``off_loop`` runs one blocking call in the read pool: its own ``READ_THREADS`` threads, not
anyio's default pool of 40 that sync routes and dependencies (``/health``, the caller guard)
share, so a page's reads never queue them; and few enough that the GIL and the memory the
frames take stay bounded when a page asks for twenty reads at once. ``OffLoop`` is the
schema extension that hands every top-level ``Query`` field to ``off_loop`` (but those marked
``INLINE``), so a plain ``def`` resolver (opening a context, a loader) never runs on the
loop; nested fields are cheap mappings or already dataloaders (which call ``off_loop``)."""

import asyncio
import inspect
from collections.abc import Callable
from functools import partial
from typing import Any
from weakref import WeakKeyDictionary

from anyio import CapacityLimiter, to_thread
from strawberry.extensions.base_extension import SchemaExtension

READ_THREADS = 6

# ``@strawberry.field(metadata=INLINE)``: a top-level resolver with no I/O, kept on the loop so
# it never queues behind a page's reads (the top bar's ``viewer`` is on every page).
INLINE = {"offload": "inline"}

# One limiter per event loop (a limiter belongs to the loop it first waits on; tests run one
# loop each).
_LIMITERS: WeakKeyDictionary[asyncio.AbstractEventLoop, CapacityLimiter] = WeakKeyDictionary()


def read_limiter() -> CapacityLimiter:
    """The read pool's limiter for the running event loop."""
    loop = asyncio.get_running_loop()
    if loop not in _LIMITERS:
        _LIMITERS[loop] = CapacityLimiter(READ_THREADS)
    return _LIMITERS[loop]


async def off_loop[T](func: Callable[..., T], *args: Any) -> T:
    """``func(*args)`` in the read pool; the event loop stays free meanwhile."""
    return await to_thread.run_sync(func, *args, limiter=read_limiter())


def _inline(info: Any) -> bool:
    """Whether the field being resolved is declared ``INLINE``."""
    found = info.schema._strawberry_schema.get_field_for_type(
        info.field_name, info.parent_type.name
    )
    return found is not None and found.metadata == INLINE


class OffLoop(SchemaExtension):
    """Runs each top-level field's resolver in the read pool. An async resolver comes back as a
    coroutine, which is then awaited on the loop (its own blocking calls use ``off_loop``).

    The top-level fields of one operation hand back their results together, once the last has
    finished: their children then resolve in one event-loop tick, so dataloaders still batch
    across sibling fields (``a: instrument(..) { features }`` ``b: instrument(..) { features }``
    is one read, not two)."""

    def __init__(self) -> None:
        self._running = 0
        self._released = asyncio.Event()

    def resolve(
        self, _next: Callable[..., Any], root: Any, info: Any, *args: Any, **kwargs: Any
    ) -> Any:
        if info.path.prev is not None or _inline(info):
            # a nested field (a mapping, or a dataloader), or one declared free of I/O
            return _next(root, info, *args, **kwargs)
        self._running += 1  # counted in the tick the siblings start in, before any finishes
        return self._top(partial(_next, root, info, *args, **kwargs))

    async def _top(self, call: Callable[[], Any]) -> Any:
        try:
            result = await off_loop(call)
            if inspect.isawaitable(result):
                result = await result
        finally:
            self._running -= 1
            if self._running == 0:
                self._released.set()
        await self._released.wait()
        return result
