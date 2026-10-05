"""The app factory: routers, the GraphQL read layer at ``POST /graphql`` (ADR 0037), CORS for
the local web dev server, the live quotes (closed when the app stops), and error handlers that
map library errors to HTTP (not found -> 404, bad configuration or parameters -> 400, a write
that clashes with what exists -> 409)."""

import json
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import date
from functools import partial

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from algotrade.core.model.errors import ConfigurationError, MissingDataError
from algotrade.services.authoring.scope import ConfigWriter, ConflictError, ScreenNotFoundError
from algotrade.services.live.quotes import LiveQuotes
from algotrade.services.ondemand.screens import OnDemandScreens, open_ondemand
from algotrade.services.read.context import (
    NotFoundError,
    ReadContext,
    ResultCache,
    StoreContext,
    open_context,
    open_stores,
)
from algotrade_api import __version__
from algotrade_api.deps import ApiSettings, ReadStore
from algotrade_api.graphql.schema import graphql_router
from algotrade_api.live import no_live, open_live
from algotrade_api.routes import ROUTERS

TITLE = "algotrade API"


def _not_found(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": str(exc)})


def _bad_request(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=400, content={"detail": str(exc)})


def _conflict(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=409, content={"detail": str(exc)})


def create_app(
    settings: ApiSettings,
    store: ReadStore | None = None,
    writer: ConfigWriter | None = None,
    live: LiveQuotes | None = None,
    ondemand: OnDemandScreens | None = None,
) -> FastAPI:
    """The API over ``store`` (default: the store and configs ``settings`` name); user
    configs are written through ``writer`` (default: the files under ``settings.config_dir``).
    ``live``: the live quotes (default: IB Gateway when ``settings.live``, else switched off).
    ``ondemand``: the on-request screen runner (default: over the store when ``settings.live``,
    the served app; else off: a request answers 400)."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        yield
        app.state.live.close()
        if app.state.ondemand is not None:
            app.state.ondemand.close()

    app = FastAPI(
        title=TITLE,
        version=__version__,
        description=(
            "Read-only API over the algotrade stores (ADR 0024); it writes only user configs "
            "and user features, through services.authoring (ADR 0029), and the live option "
            "quotes it served, to live/* tables (ADR 0028); a screener run on request writes its "
            "results as the nightly does (ADR 0033)."
        ),
        lifespan=lifespan,
    )
    app.state.store = store if store is not None else settings.open()
    app.state.writer = writer if writer is not None else settings.open_writer()
    if live is None:
        live = open_live(settings.data_url, app.state.store.configs) if settings.live else no_live()
    app.state.live = live
    if ondemand is None and settings.live:
        ondemand = open_ondemand(settings.data_url, app.state.store.configs)
    app.state.ondemand = ondemand
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_methods=["GET", "PUT", "POST", "DELETE"],
        allow_headers=["*"],
    )
    app.add_exception_handler(NotFoundError, _not_found)
    app.add_exception_handler(MissingDataError, _not_found)
    app.add_exception_handler(ScreenNotFoundError, _not_found)
    app.add_exception_handler(ConflictError, _conflict)
    app.add_exception_handler(ConfigurationError, _bad_request)
    for router in ROUTERS:
        app.include_router(router)
    cache = ResultCache(READ_CACHE_SIZE)
    reads, stores = _reads(app.state.store, cache), _stores(app.state.store, cache)
    app.include_router(graphql_router(reads, settings.debug, stores))
    return app


READ_CACHE_SIZE = 32


def _reads(store: ReadStore, cache: ResultCache) -> Callable[[date | None], ReadContext]:
    """Opens a GraphQL request's read context over ``store`` for a requested session, with
    one result cache for every request of the app (entries keyed on the published state;
    room for the session, the descriptions, the universe and a few table orders)."""
    return partial(open_context, store.reader, store.configs, store.user, cache=cache)


def _stores(store: ReadStore, cache: ResultCache) -> Callable[[], StoreContext]:
    """Opens a GraphQL request's session-free context over ``store`` (configs, run records,
    the catalogue: they need no stored market data)."""
    return partial(open_stores, store.reader, store.configs, store.user, cache=cache)


def openapi_json() -> str:
    """The OpenAPI document as committed in ``apps/api/openapi.json`` (stable formatting)."""
    app = create_app(ApiSettings("memory://", "config"))
    return json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n"
