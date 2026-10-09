"""The schema and its router (ADR 0037): the ``Query`` root (``types/query.py``) over the
read model, the scalars, the document limits, ``OffLoop`` (top-level fields run off the event
loop), and ``graphql_router``, mounted by ``create_app`` at ``POST /graphql`` (GET off;
the GraphiQL IDE only when ``ApiSettings.debug``). Every error in a response carries
``extensions.code`` (``errors.py``). ``sdl()`` is the committed snapshot
``apps/api/schema.graphql`` (``scripts/export_graphql_schema.py``)."""

import json
from collections.abc import Callable, Hashable
from typing import Any, cast

import strawberry
from fastapi import Request, Response
from fastapi.routing import APIWebSocketRoute
from strawberry.fastapi import GraphQLRouter
from strawberry.http import GraphQLHTTPResponse
from strawberry.schema.config import StrawberryConfig
from strawberry.types import ExecutionResult

from algotrade.config.site.users import Role
from algotrade_api.graphql.context import Opener, RequestContext, StoresOpener, context_getter
from algotrade_api.graphql.errors import response_of
from algotrade_api.graphql.limits import EXTENSIONS
from algotrade_api.graphql.offload import Admission, OffLoop, only_inline
from algotrade_api.graphql.response_cache import (
    ResponseCache,
    WriteEpoch,
    cacheable,
    operation_name,
    response_key,
)
from algotrade_api.graphql.scalars import SCALARS
from algotrade_api.graphql.types.query import Query

PATH = "/graphql"

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
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self._seq, self._epoch, self._cache, self._admission = seq, epoch, cache, admission

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
            key = response_key(self._seq(), self._epoch.value, viewer, document, variables, name)
            body = self._cache.get(key)
            if body is not None:
                return Response(body, media_type="application/json")
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
            self._cache.put(key, bytes(response.body))
        return response


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
) -> GraphQLRouter[RequestContext, None]:
    """``POST /graphql`` over the read contexts ``opener`` opens (one per requested session,
    per request) and the session-free one ``stores`` opens (configs, run records); the
    GraphiQL IDE at ``GET /graphql`` only when ``debug``. ``seq`` is the published state
    (``StoreReader.visible_seq``) the response cache keys on; ``epoch`` the writes served."""
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
    )
    # No subscriptions: drop Strawberry's WebSocket route, which the caller guard (an HTTP
    # dependency, ADR 0040) cannot see; /graphql is served over HTTP POST only.
    router.routes = [r for r in router.routes if not isinstance(r, APIWebSocketRoute)]
    return router
