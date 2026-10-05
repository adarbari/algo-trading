"""The schema and its router (ADR 0037): the ``Query`` root (``types/query.py``) over the
read model, the scalars, the document limits, and ``graphql_router``, mounted by
``create_app`` at ``POST /graphql`` (GET off; the GraphiQL IDE only when
``ApiSettings.debug``). Every error in a response
carries ``extensions.code`` (``errors.py``). ``sdl()`` is the committed snapshot
``apps/api/schema.graphql`` (``scripts/export_graphql_schema.py``)."""

import strawberry
from fastapi import Request
from strawberry.fastapi import GraphQLRouter
from strawberry.http import GraphQLHTTPResponse
from strawberry.schema.config import StrawberryConfig
from strawberry.types import ExecutionResult

from algotrade_api.graphql.context import Opener, RequestContext, StoresOpener, context_getter
from algotrade_api.graphql.errors import response_of
from algotrade_api.graphql.limits import EXTENSIONS
from algotrade_api.graphql.scalars import SCALARS
from algotrade_api.graphql.types.query import Query

PATH = "/graphql"

schema = strawberry.Schema(
    query=Query,
    extensions=list(EXTENSIONS),
    config=StrawberryConfig(scalar_map=SCALARS),
)


def sdl() -> str:
    """The schema as SDL, as committed in ``apps/api/schema.graphql``."""
    return schema.as_str() + "\n"


class _Router(GraphQLRouter[RequestContext, None]):
    """Strawberry's FastAPI router with an ``extensions.code`` on every error."""

    async def process_result(
        self, request: Request, result: ExecutionResult
    ) -> GraphQLHTTPResponse:
        return response_of(result)


def graphql_router(
    opener: Opener, debug: bool = False, stores: StoresOpener | None = None
) -> GraphQLRouter[RequestContext, None]:
    """``POST /graphql`` over the read contexts ``opener`` opens (one per requested session,
    per request) and the session-free one ``stores`` opens (configs, run records); the
    GraphiQL IDE at ``GET /graphql`` only when ``debug``."""
    return _Router(
        schema,
        path=PATH,
        graphql_ide="graphiql" if debug else None,
        allow_queries_via_get=False,
        context_getter=context_getter(opener, stores),
        tags=["graphql"],
    )
