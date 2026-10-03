"""The app factory: routers, CORS for the local web dev server, and error handlers that map
library errors to HTTP (not found -> 404, bad configuration or parameters -> 400)."""

import json

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from algotrade.core.model.errors import ConfigurationError, MissingDataError
from algotrade.services.explore.store import NotFoundError, ReadStore
from algotrade_api import __version__
from algotrade_api.deps import ApiSettings
from algotrade_api.routes import ROUTERS

TITLE = "algotrade API"


def _not_found(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": str(exc)})


def _bad_request(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=400, content={"detail": str(exc)})


def create_app(settings: ApiSettings, store: ReadStore | None = None) -> FastAPI:
    """The API over ``store`` (default: the store and configs ``settings`` name)."""
    app = FastAPI(
        title=TITLE,
        version=__version__,
        description="Read-only API over the algotrade stores (ADR 0025).",
    )
    app.state.store = store if store is not None else settings.open()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_methods=["GET"],
        allow_headers=["*"],
    )
    app.add_exception_handler(NotFoundError, _not_found)
    app.add_exception_handler(MissingDataError, _not_found)
    app.add_exception_handler(ConfigurationError, _bad_request)
    for router in ROUTERS:
        app.include_router(router)
    return app


def openapi_json() -> str:
    """The OpenAPI document as committed in ``apps/api/openapi.json`` (stable formatting)."""
    app = create_app(ApiSettings("memory://", "config"))
    return json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n"
