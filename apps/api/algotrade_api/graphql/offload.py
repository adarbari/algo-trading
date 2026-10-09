"""Keeps blocking work off the API's event loop (ADR 0037): every read of the graph is parquet
and pandas work, and a resolver that does it on the loop stalls every other request, ``/health``
included (the hosted API took 28-36 s to answer it during a page load).

``off_loop`` runs one blocking call in the read pool: its own ``READ_THREADS`` threads, not
anyio's default pool of 40 that sync routes and dependencies (``/health``, the caller guard)
share, so a page's reads never queue them; and few enough that the GIL and the memory the
frames take stay bounded when a page asks for twenty reads at once. ``OffLoop`` is the
schema extension that hands every top-level ``Query`` field to ``off_loop`` (but those marked
``INLINE``), so a plain ``def`` resolver (opening a context, a loader) never runs on the
loop; nested fields are cheap mappings or already dataloaders (which call ``off_loop``).

``Admission`` is the front of the pool (owner decision 2026-10-09): at most ``READ_THREADS``
requests read and ``MAX_WAITING`` wait; the next one is refused with ``OverloadedError`` (the
API answers 503 + ``Retry-After``) instead of queueing without bound, so memory and CPU stay
bounded under hundreds of concurrent requests. Counted in one event-loop tick (no race), and
released when the request ends."""

import asyncio
import inspect
from collections.abc import Callable
from functools import lru_cache, partial
from typing import Any
from weakref import WeakKeyDictionary

from anyio import CapacityLimiter, to_thread
from graphql import FieldNode, GraphQLError, OperationDefinitionNode, parse
from strawberry.extensions.base_extension import SchemaExtension

READ_THREADS = 6
MAX_WAITING = 32  # requests waiting for a read thread; beyond it the API answers 503
RETRY_AFTER_S = 2  # what a refused request is told to wait (``Retry-After``)

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


class OverloadedError(Exception):
    """The read pool is full (``Admission``): the API answers 503 with ``retry_after_s``."""

    def __init__(self, retry_after_s: int = RETRY_AFTER_S) -> None:
        self.retry_after_s = retry_after_s
        super().__init__(f"the API is busy, try again in {retry_after_s} s")


class Admission:
    """The bounded queue in front of the read pool: ``admit()`` takes a place for one request
    (``OverloadedError`` when ``READ_THREADS + MAX_WAITING`` are taken), ``release()`` gives it
    back. Plain counters, touched only on the event loop."""

    def __init__(self, limit: int = READ_THREADS + MAX_WAITING) -> None:
        self.limit = limit
        self.taken = 0

    def admit(self) -> None:
        if self.taken >= self.limit:
            raise OverloadedError
        self.taken += 1

    def release(self) -> None:
        self.taken -= 1


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
    is one read, not two). The price: a fast field's nested reads start only when the slowest
    top-level field is done (latency max(top) + max(nested)); do not release them earlier, that
    breaks the batching. No deadlock: a failure or cancel still counts the field down."""

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


@lru_cache(maxsize=256)
def only_inline(schema: Any, document: str) -> bool:
    """Whether every top-level field of ``document`` is declared ``INLINE`` (the top bar's
    ``viewer``): such a request does no I/O and is never refused by ``Admission``. A document
    that does not parse, or uses a fragment at the top level, is not."""
    try:
        operations = [
            d for d in parse(document).definitions if isinstance(d, OperationDefinitionNode)
        ]
    except GraphQLError:
        return False
    if not operations:
        return False
    for operation in operations:
        for selection in operation.selection_set.selections:
            if not isinstance(selection, FieldNode):
                return False
            found = schema.get_field_for_type(selection.name.value, "Query")
            if found is None or found.metadata != INLINE:
                return False
    return True
