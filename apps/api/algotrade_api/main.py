"""The app factory: routers, the GraphQL read layer at ``POST /graphql`` (ADR 0037), the
authenticator every route but ``GET /health`` resolves its caller through (ADR 0040: no or
bad token -> 401, a caller the registry refuses -> 403), CORS for the local web dev server
(outermost, so a 401 still carries it), the live quotes (closed when the app stops), and error
handlers that map library errors to HTTP (not found -> 404, bad configuration or parameters
-> 400, a write that clashes with what exists -> 409, the drafting model off or not answering
-> 503)."""

import json
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import date
from functools import partial

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from algotrade.config.site.settings import load_users
from algotrade.config.site.users import Role, UserRecord
from algotrade.config.user import DEFAULT_USER, UserContext
from algotrade.core.model.errors import ConfigurationError, MissingDataError, ModelUnavailableError
from algotrade.services.authoring.scope import ConfigWriter, ConflictError, ScreenNotFoundError
from algotrade.services.drafting.model import TextModel
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
from algotrade_api.auth.local import LocalAuthenticator
from algotrade_api.auth.mode import open_authenticator
from algotrade_api.auth.protocol import Authenticator
from algotrade_api.deps import ApiSettings, ReadStore, get_caller
from algotrade_api.drafting import OFF as DRAFTING_OFF
from algotrade_api.drafting import open_drafting
from algotrade_api.graphql.schema import graphql_router
from algotrade_api.live import no_live, open_live
from algotrade_api.routes import PUBLIC_ROUTERS, ROUTERS

TITLE = "algotrade API"


def _not_found(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": str(exc)})


def _bad_request(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=400, content={"detail": str(exc)})


def _conflict(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=409, content={"detail": str(exc)})


def _unavailable(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=503, content={"detail": str(exc)})


def create_app(
    settings: ApiSettings,
    store: ReadStore | None = None,
    writer: ConfigWriter | None = None,
    live: LiveQuotes | None = None,
    ondemand: OnDemandScreens | None = None,
    authenticator: Authenticator | None = None,
    drafter: TextModel | None = None,
) -> FastAPI:
    """The API over ``store`` (default: the store and configs ``settings`` name); user
    configs are written through ``writer`` (default: the files under ``settings.config_dir``).
    ``live``: the live quotes (default: IB Gateway when ``settings.live``, else switched off).
    ``ondemand``: the on-request screen runner (default: over the store when ``settings.live``,
    the served app; else off: a request answers 400). ``authenticator``: who is calling
    (default: ``settings.auth`` over the store's user registry; ADR 0040). ``drafter``: the
    text model behind screener drafts (default: the one ``config/site/llm.toml`` enables
    when ``settings.live``, else off: a request answers 503; ADR 0041)."""

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
    if authenticator is None:
        users = load_users(app.state.store.configs)
        authenticator = open_authenticator(settings.auth, users, settings.user)
    app.state.authenticator = authenticator
    if drafter is None and settings.live:
        drafter = open_drafting(app.state.store.configs)
    app.state.drafter, app.state.drafter_off = drafter, DRAFTING_OFF
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
    app.add_exception_handler(ModelUnavailableError, _unavailable)
    for router in PUBLIC_ROUTERS:
        app.include_router(router)
    caller = [Depends(get_caller)]
    for router in ROUTERS:
        app.include_router(router, dependencies=caller)
    cache = ResultCache(READ_CACHE_SIZE)
    reads, stores = _reads(app.state.store, cache), _stores(app.state.store, cache)
    app.include_router(graphql_router(reads, settings.debug, stores), dependencies=caller)
    return app


READ_CACHE_SIZE = 32


def _reads(
    store: ReadStore, cache: ResultCache
) -> Callable[[UserContext, date | None], ReadContext]:
    """Opens a GraphQL request's read context over ``store`` for its caller and a requested
    session, with one result cache for every request of the app (entries keyed on the
    published state, and on the user where the result is the user's; room for the session,
    the descriptions, the universe and a few table orders)."""
    return partial(open_context, store.reader, store.configs, cache=cache)


def _stores(store: ReadStore, cache: ResultCache) -> Callable[[UserContext], StoreContext]:
    """Opens a GraphQL request's session-free context over ``store`` for its caller (configs,
    run records, the catalogue: they need no stored market data)."""
    return partial(open_stores, store.reader, store.configs, cache=cache)


def openapi_json() -> str:
    """The OpenAPI document as committed in ``apps/api/openapi.json`` (stable formatting)."""
    local = LocalAuthenticator(UserRecord(DEFAULT_USER, Role.ADMIN))  # serves no request
    app = create_app(ApiSettings("memory://", "config"), authenticator=local)
    return json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n"
