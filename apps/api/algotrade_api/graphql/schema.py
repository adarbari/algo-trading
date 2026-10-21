"""The schema and its router (ADR 0037): the ``Query`` root (``types/query.py``) over the
read model, the scalars, the document limits, ``OffLoop`` (top-level fields run off the event
loop), and ``graphql_router``, mounted by ``create_app`` at ``POST /graphql`` (GET off;
the GraphiQL IDE only when ``ApiSettings.debug``). Every error in a response carries
``extensions.code`` (``errors.py``). ``sdl()`` is the committed snapshot
``apps/api/schema.graphql`` (``scripts/export_graphql_schema.py``)."""

import asyncio
import gzip
import json
import logging
import time
from collections.abc import Callable, Hashable
from datetime import UTC, date, datetime
from typing import Any, cast

import strawberry
from fastapi import Request, Response
from fastapi.routing import APIWebSocketRoute
from strawberry.fastapi import GraphQLRouter
from strawberry.http import GraphQLHTTPResponse
from strawberry.schema.config import StrawberryConfig
from strawberry.types import ExecutionResult

from algotrade.config.site.users import Role, UserRecord
from algotrade.core.time.calendar import exchange_date, last_closed_session
from algotrade_api.graphql.context import Opener, RequestContext, StoresOpener, context_getter
from algotrade_api.graphql.errors import response_of
from algotrade_api.graphql.limits import EXTENSIONS
from algotrade_api.graphql.offload import (
    READ_THREADS,
    Admission,
    OffLoop,
    OverloadedError,
    off_loop,
    only_inline,
)
from algotrade_api.graphql.response_cache import (
    CLOSED_SESSION_OPERATIONS,
    RUN_OPERATIONS,
    SHARED_OPERATIONS,
    TODAY_OPERATIONS,
    OperationLog,
    ResponseCache,
    Served,
    WriteEpoch,
    cacheable,
    operation_name,
    response_key,
)
from algotrade_api.graphql.scalars import SCALARS
from algotrade_api.graphql.types.query import Query

REPLAY_BUDGET_S = 30.0  # the longest one replay pass takes (start, or after a publish)
_logger = logging.getLogger(__name__)
PATH = "/graphql"
GZIP_LEVEL = 5  # a cached answer is compressed once and read many times

schema = strawberry.Schema(
    query=Query,
    extensions=[*EXTENSIONS, OffLoop],
    config=StrawberryConfig(scalar_map=SCALARS),
)


def sdl() -> str:
    """The schema as SDL, as committed in ``apps/api/schema.graphql``."""
    return schema.as_str() + "\n"


class CachingRouter(GraphQLRouter[RequestContext, None]):
    """Strawberry's FastAPI router with an ``extensions.code`` on every error, a response cache
    (``response_cache.py``) and the admission control in front of the read
    pool (``offload.Admission``: a request past the queue raises ``OverloadedError``)."""

    def __init__(
        self,
        *args: Any,
        seq: Callable[[], int],
        epoch: WriteEpoch,
        config_generation: Callable[[str], int | None],
        cache: ResponseCache,
        admission: Admission,
        runs: Callable[[], tuple[int, int]],
        closed: Callable[[], date],
        served: Callable[[], str],
        opener: Opener,
        stores: StoresOpener | None,
        log: OperationLog,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self._opener, self._stores_opener, self._log = opener, stores, log
        self._revalidating: dict[str, asyncio.Task[None]] = {}
        self._seq, self._epoch, self._cache, self._admission = seq, epoch, cache, admission
        self._runs, self._closed, self._served = runs, closed, served
        self._config_generation = config_generation

    async def process_result(
        self, request: Request, result: ExecutionResult
    ) -> GraphQLHTTPResponse:
        viewer = getattr(request.state, "viewer", None)
        request.state.failed = bool(result.errors)  # a failed or partial answer is never kept
        return response_of(result, viewer is not None and viewer.role is Role.ADMIN)

    async def run(self, request: Any, *args: Any, **kwargs: Any) -> Any:
        if not isinstance(request, Request) or request.method != "POST":
            return await super().run(request, *args, **kwargs)
        parsed = await _operation(request)
        viewer = getattr(request.state, "viewer", None)
        key = None
        if parsed is not None and viewer is not None and cacheable(parsed[0]):
            document, variables = parsed
            self._log.note(viewer, document, variables)
            key = await self._key(viewer, document, variables)
            body = self._cache.get(key) if key is not None else None
            if body is not None:
                return await _served(body, request)
            stale = self._cache.get_stale(key) if key is not None else None
            if stale is not None and key is not None:  # stale-while-revalidate: answer now,
                self._revalidate(key, Served(viewer, document, variables))  # recompute behind it
                return await _served(stale, request)
        inline = parsed is not None and only_inline(cast(Hashable, self.schema), parsed[0])
        if not inline:
            self._admission.admit()
        try:
            response = await super().run(request, *args, **kwargs)
        finally:
            if not inline:
                self._admission.release()
        failed = getattr(request.state, "failed", True)
        if key is not None and response.status_code == 200 and not failed:
            packed = await asyncio.to_thread(gzip.compress, bytes(response.body), GZIP_LEVEL)
            self._cache.put(key, packed)
            return await _served(packed, request)
        return response

    def _generation(self, viewer: UserRecord, name: str | None) -> int | None:
        """The viewer's config generation, read before the answer is computed; ``None`` when a
        write of theirs is in flight or the counter cannot be read: nothing is cached then
        (ADR 0077 decision 15)."""
        if name in SHARED_OPERATIONS:
            return 0
        return self._config_generation(viewer.user_id)

    async def _key(self, viewer: UserRecord, document: str, variables: Any) -> str | None:
        """The cache key of this operation for ``viewer`` now (``None``: not cacheable at this
        moment); every state the answer depends on is read before it is computed (ADR 0022)."""
        name = operation_name(document)
        generation = self._generation(viewer, name)
        if generation is None:
            return None
        served = await off_loop(self._served)  # resolved once per publish / saved record
        return response_key(
            self._seq(),
            self._epoch.value,
            viewer,
            document,
            variables,
            name,
            self._runs() if name in RUN_OPERATIONS else (0, 0),
            self._closed() if name in CLOSED_SESSION_OPERATIONS else None,
            served,
            exchange_date(datetime.now(UTC)) if name in TODAY_OPERATIONS else None,
            generation,
        )

    def _revalidate(self, key: str, op: Served) -> None:
        """Recompute ``op`` in the background (one at a time per key; a stale hit while it runs
        is served stale again)."""
        if key in self._revalidating:
            return
        task = asyncio.create_task(self._revalidated(op))
        self._revalidating[key] = task
        task.add_done_callback(lambda _t: self._revalidating.pop(key, None))

    async def _revalidated(self, op: Served) -> None:
        try:
            await self.refresh(op)
        except Exception:  # a store mid-publish: the next stale hit tries again
            _logger.exception("recomputing %s failed", operation_name(op.document))

    async def aclose(self) -> None:
        """Cancel the recomputes still running (the app is stopping) and wait for them."""
        tasks = list(self._revalidating.values())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    async def refresh(self, op: Served, only_missing: bool = False) -> bool | None:
        """Run ``op`` in process as its caller and keep the answer under the key read before it
        ran (the replay of the warmer and of a stale hit); with ``only_missing`` a fresh entry is
        left alone. False when it was skipped or refused (a busy pool), None when it failed (never
        kept)."""
        key = await self._key(op.viewer, op.document, op.variables)
        if key is None:  # a write of the caller's is in flight: nothing to keep
            return False
        if only_missing and self._cache.get(key) is not None:
            return False
        context = RequestContext(self._opener, op.viewer, self._stores_opener)
        try:
            self._admission.admit()
        except OverloadedError:
            return False
        try:
            result = await self.schema.execute(
                op.document, variable_values=op.variables, context_value=context
            )
        finally:
            self._admission.release()
        if result.errors:
            return None
        body = self.encode_json(response_of(result, op.viewer.role is Role.ADMIN))
        raw = body if isinstance(body, bytes) else body.encode()
        self._cache.put(key, await asyncio.to_thread(gzip.compress, raw, GZIP_LEVEL))
        return True

    async def replay(
        self, ops: list[Served] | None = None, budget_s: float = REPLAY_BUDGET_S
    ) -> int:
        """Recompute, one after the other (the pool is shared with the pages), every operation
        ``ops`` names (default: the log) whose answer is not fresh; how many were recomputed.
        Stops after ``budget_s``, and while the read pool is busy with requests (the next
        publish tries again); an operation that fails is dropped from the log."""
        done = 0
        deadline = time.monotonic() + budget_s
        for op in ops if ops is not None else self._log.items():
            if time.monotonic() > deadline or self._admission.taken >= READ_THREADS:
                break
            try:
                outcome = await self.refresh(op, only_missing=True)
            except Exception:
                _logger.exception("replaying %s failed", operation_name(op.document))
                outcome = None
            if outcome is None:
                self._log.discard(op)
            else:
                done += outcome
        return done


async def _served(packed: bytes, request: Request) -> Response:
    """A cached (gzip) body as the answer: as is, with ``Content-Encoding: gzip``, when the
    client accepts gzip (the ``GZipMiddleware`` leaves an encoded response alone, so nothing
    is compressed per hit); else inflated off the event loop (bounded: one pass over a body
    the cache already bounds, and only for a client that cannot read gzip)."""
    headers = {"Vary": "Accept-Encoding"}
    if _accepts_gzip(request.headers.get("accept-encoding", "")):
        headers["Content-Encoding"] = "gzip"
        return Response(packed, media_type="application/json", headers=headers)
    body = await asyncio.to_thread(gzip.decompress, packed)
    return Response(body, media_type="application/json", headers=headers)


def _accepts_gzip(header: str) -> bool:
    """Whether an ``Accept-Encoding`` value allows gzip (a listed ``gzip`` or ``*``, not q=0)."""
    for item in header.split(","):
        coding, _, params = item.partition(";")
        if coding.strip().lower() in ("gzip", "*"):
            return params.replace(" ", "").lower() not in ("q=0", "q=0.0", "q=0.00", "q=0.000")
    return False


async def _operation(request: Request) -> tuple[str, Any] | None:
    """The document and variables of a single-operation JSON POST; ``None`` for anything else
    (a batch, a multipart upload, a body that is not JSON)."""
    if "application/json" not in request.headers.get("content-type", ""):
        return None
    try:
        data = json.loads(await request.body())
    except ValueError:
        return None
    if not isinstance(data, dict) or not isinstance(data.get("query"), str):
        return None
    return data["query"], data.get("variables")


def graphql_router(
    opener: Opener,
    debug: bool = False,
    stores: StoresOpener | None = None,
    seq: Callable[[], int] = lambda: 0,
    epoch: WriteEpoch | None = None,
    cache: ResponseCache | None = None,
    admission: Admission | None = None,
    runs: Callable[[], tuple[int, int]] = lambda: (0, 0),
    closed: Callable[[], date] = lambda: last_closed_session(datetime.now(UTC)),
    served: Callable[[], str] = lambda: "",
    log: OperationLog | None = None,
    config_generation: Callable[[str], int | None] = lambda user: 0,
) -> CachingRouter:
    """``POST /graphql`` over the read contexts ``opener`` opens (one per requested session,
    per request) and the session-free one ``stores`` opens (configs, run records); the
    GraphiQL IDE at ``GET /graphql`` only when ``debug``. ``seq`` is the published state
    (``StoreReader.visible_seq``) the response cache keys on; ``epoch`` the writes served,
    ``config_generation`` a user's durable config counter (ADR 0077 decision 15),
    ``runs`` the runs generation (``StoreReader.runs_generation``) and ``closed`` the last
    closed session, which the keys of the run-dependent operations hold; ``served`` the token of
    the default session (``served_token``) every key holds (ADR 0062)."""
    router = CachingRouter(
        schema,
        path=PATH,
        graphql_ide="graphiql" if debug else None,
        allow_queries_via_get=False,
        context_getter=context_getter(opener, stores),
        tags=["graphql"],
        seq=seq,
        epoch=epoch if epoch is not None else WriteEpoch(),
        config_generation=config_generation,
        cache=cache if cache is not None else ResponseCache(),
        admission=admission if admission is not None else Admission(),
        runs=runs,
        closed=closed,
        served=served,
        opener=opener,
        stores=stores,
        log=log if log is not None else OperationLog(),
    )
    # No subscriptions: drop Strawberry's WebSocket route, which the caller guard (an HTTP
    # dependency, ADR 0040) cannot see; /graphql is served over HTTP POST only.
    router.routes = [r for r in router.routes if not isinstance(r, APIWebSocketRoute)]
    return router
