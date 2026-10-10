"""The schema and its router (ADR 0037): the ``Query`` root (``types/query.py``) over the
read model, the scalars, the document limits, ``OffLoop`` (top-level fields run off the event
loop), and ``graphql_router``, mounted by ``create_app`` at ``POST /graphql`` (GET off;
the GraphiQL IDE only when ``ApiSettings.debug``). Every error in a response carries
``extensions.code`` (``errors.py``). ``sdl()`` is the committed snapshot
``apps/api/schema.graphql`` (``scripts/export_graphql_schema.py``)."""

import asyncio
import gzip
import json
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

from algotrade.config.site.users import Role
from algotrade.core.time.calendar import last_closed_session
from algotrade_api.graphql.context import Opener, RequestContext, StoresOpener, context_getter
from algotrade_api.graphql.errors import response_of
from algotrade_api.graphql.limits import EXTENSIONS
from algotrade_api.graphql.offload import Admission, OffLoop, off_loop, only_inline
from algotrade_api.graphql.response_cache import (
    CLOSED_SESSION_OPERATIONS,
    RUN_OPERATIONS,
    ResponseCache,
    WriteEpoch,
    cacheable,
    operation_name,
    response_key,
)
from algotrade_api.graphql.scalars import SCALARS
from algotrade_api.graphql.types.query import Query

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


class _Router(GraphQLRouter[RequestContext, None]):
    """Strawberry's FastAPI router with an ``extensions.code`` on every error, a response cache
    (``response_cache.py``) and the admission control in front of the read
    pool (``offload.Admission``: a request past the queue raises ``OverloadedError``)."""

    def __init__(
        self,
        *args: Any,
        seq: Callable[[], int],
        epoch: WriteEpoch,
        cache: ResponseCache,
        admission: Admission,
        runs: Callable[[], tuple[int, int]],
        closed: Callable[[], date],
        served: Callable[[], str],
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self._seq, self._epoch, self._cache, self._admission = seq, epoch, cache, admission
        self._runs, self._closed, self._served = runs, closed, served

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
            name = operation_name(document)
            # every state the answer depends on is read before it is computed (ADR 0022)
            served = await off_loop(self._served)  # resolved once per publish / saved record
            key = response_key(
                self._seq(),
                self._epoch.value,
                viewer,
                document,
                variables,
                name,
                self._runs() if name in RUN_OPERATIONS else (0, 0),
                self._closed() if name in CLOSED_SESSION_OPERATIONS else None,
                served,
            )
            body = self._cache.get(key)
            if body is not None:
                return await _served(body, request)
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
) -> GraphQLRouter[RequestContext, None]:
    """``POST /graphql`` over the read contexts ``opener`` opens (one per requested session,
    per request) and the session-free one ``stores`` opens (configs, run records); the
    GraphiQL IDE at ``GET /graphql`` only when ``debug``. ``seq`` is the published state
    (``StoreReader.visible_seq``) the response cache keys on; ``epoch`` the writes served,
    ``runs`` the runs generation (``StoreReader.runs_generation``) and ``closed`` the last
    closed session, which the keys of the run-dependent operations hold; ``served`` the token of
    the default session (``served_token``) every key holds (ADR 0062)."""
    router = _Router(
        schema,
        path=PATH,
        graphql_ide="graphiql" if debug else None,
        allow_queries_via_get=False,
        context_getter=context_getter(opener, stores),
        tags=["graphql"],
        seq=seq,
        epoch=epoch if epoch is not None else WriteEpoch(),
        cache=cache if cache is not None else ResponseCache(),
        admission=admission if admission is not None else Admission(),
        runs=runs,
        closed=closed,
        served=served,
    )
    # No subscriptions: drop Strawberry's WebSocket route, which the caller guard (an HTTP
    # dependency, ADR 0040) cannot see; /graphql is served over HTTP POST only.
    router.routes = [r for r in router.routes if not isinstance(r, APIWebSocketRoute)]
    return router
