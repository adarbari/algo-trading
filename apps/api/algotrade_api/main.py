"""The app factory: routers, the GraphQL read layer at ``POST /graphql`` (ADR 0037), the
authenticator every route but ``GET /health`` resolves its caller through (ADR 0040: no or
bad token -> 401, a caller the registry refuses -> 403), CORS for the configured web origins
(outermost, so a 401 still carries it), the live quotes (closed when the app stops), and error
handlers that map library errors to HTTP (not found -> 404, bad configuration or parameters
-> 400, another user's job -> 403, a write that clashes with what exists -> 409, the drafting
model off or not answering -> 503), and, when ``settings.web_dist`` is set, the built web app
on the same origin (``web``, ADR 0044: mounted last, so every API route keeps precedence);
the build identity it started with (``ops/build.py``) is taken here, once."""

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
from algotrade.core.model.errors import (
    ConfigurationError,
    MissingDataError,
    ModelUnavailableError,
    PermissionDeniedError,
    RateLimitedError,
)
from algotrade.services.authoring.scope import ConfigWriter, ConflictError, ScreenNotFoundError
from algotrade.services.explaining.cache import open_text_cache
from algotrade.services.explaining.limits import RateLimiter
from algotrade.services.live.quotes import LiveQuotes
from algotrade.services.ondemand.screens import OnDemandScreens, open_ondemand
from algotrade.services.read.availability.cause import (
    GENERIC_REASONS,
    UnavailableKind,
    names_a_table,
)
from algotrade.services.read.context import (
    NotFoundError,
    ReadContext,
    ResultCache,
    StoreContext,
    open_context,
    open_stores,
)
from algotrade.services.text_model.model import TextModel
from algotrade_api import __version__
from algotrade_api.auth.local import LocalAuthenticator
from algotrade_api.auth.mode import open_authenticator
from algotrade_api.auth.protocol import Authenticator
from algotrade_api.deps import ApiSettings, ReadStore, get_caller, is_admin_request
from algotrade_api.graphql.schema import graphql_router, sdl
from algotrade_api.live import no_live, open_live
from algotrade_api.ops.build import api_stamp
from algotrade_api.routes import PUBLIC_ROUTERS, ROUTERS
from algotrade_api.text_model import OFF as TEXT_MODEL_OFF
from algotrade_api.text_model import open_text_model
from algotrade_api.web import web_router

TITLE = "algotrade API"


def _not_found(request: Request, exc: Exception) -> JSONResponse:
    """404 with the text for an admin; for anyone else the data behind a missing table or a
    stored table's path is "not available because of a system error" (ADR 0056)."""
    text = str(exc)
    if (isinstance(exc, MissingDataError) or names_a_table(text)) and not is_admin_request(request):
        text = GENERIC_REASONS[UnavailableKind.SYSTEM]
    return JSONResponse(status_code=404, content={"detail": text})


def _bad_request(request: Request, exc: Exception) -> JSONResponse:
    text = str(exc)
    if names_a_table(text) and not is_admin_request(request):
        text = GENERIC_REASONS[UnavailableKind.SYSTEM]
    return JSONResponse(status_code=400, content={"detail": text})


def _conflict(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=409, content={"detail": str(exc)})


def _forbidden(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=403, content={"detail": str(exc)})


def _unavailable(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=503, content={"detail": str(exc)})


def _rate_limited(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RateLimitedError)
    return JSONResponse(
        status_code=429,
        content={"detail": str(exc)},
        headers={"Retry-After": str(exc.retry_after_s)},
    )


def create_app(
    settings: ApiSettings,
    store: ReadStore | None = None,
    writer: ConfigWriter | None = None,
    live: LiveQuotes | None = None,
    ondemand: OnDemandScreens | None = None,
    authenticator: Authenticator | None = None,
    text_model: TextModel | None = None,
) -> FastAPI:
    """The API over ``store`` (default: the store and configs ``settings`` name); user
    configs are written through ``writer`` (default: the files under ``settings.config_dir``).
    ``live``: the live quotes (default: IB Gateway when ``settings.live``, else switched off).
    ``ondemand``: the on-request screen runner (default: over the store when ``settings.live``,
    the served app; else off: a request answers 400). ``authenticator``: who is calling
    (default: ``settings.auth`` over the store's user registry; ADR 0040). ``text_model``: the
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
    app.state.build = api_stamp(sdl())  # the code and schema this process serves until restarted
    app.state.web_dist = settings.web_dist
    app.state.store = store if store is not None else settings.open()
    app.state.writer = writer if writer is not None else settings.open_writer()
    if live is None:
        live = open_live(settings.data_url, app.state.store.configs) if settings.live else no_live()
    app.state.live = live
    if ondemand is None and settings.live:
        ondemand = open_ondemand(settings.data_url, app.state.store.configs)
    app.state.ondemand = ondemand
    users = load_users(app.state.store.configs)
    app.state.users = users
    if authenticator is None:
        authenticator = open_authenticator(settings.auth, users, settings.user)
    app.state.authenticator = authenticator
    text_model_off = TEXT_MODEL_OFF
    if text_model is None and settings.live:
        text_model, text_model_off = open_text_model(app.state.store.configs)
    app.state.text_model, app.state.text_model_off = text_model, text_model_off
    app.state.explain_cache = open_text_cache(settings.data_url)  # ADR 0041 (amended): derived
    app.state.explain_limiter = RateLimiter()
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
    app.add_exception_handler(PermissionDeniedError, _forbidden)
    app.add_exception_handler(ModelUnavailableError, _unavailable)
    app.add_exception_handler(RateLimitedError, _rate_limited)
    for router in PUBLIC_ROUTERS:
        app.include_router(router)
    caller = [Depends(get_caller)]
    for router in ROUTERS:
        app.include_router(router, dependencies=caller)
    cache = ResultCache(READ_CACHE_SIZE)
    reads, stores = _reads(app.state.store, cache), _stores(app.state.store, cache)
    app.include_router(graphql_router(reads, settings.debug, stores), dependencies=caller)
    if settings.web_dist is not None:  # last: its catch-all GET must not shadow an API route
        app.include_router(web_router(settings.web_dist))
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
