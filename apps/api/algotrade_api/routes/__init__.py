"""One router per area: parse parameters, call ONE library function (under ``authoring/``, one
``services.authoring`` write, ADR 0029; under ``preview/``, one ``services.preview`` dry run of
unsaved input; else a job, the live quotes or the health check),
map it to a response schema. No business logic here (ADR 0024); ``ROUTERS`` is what
``main.create_app`` mounts."""

from fastapi import APIRouter

from algotrade_api.routes import chains, health
from algotrade_api.routes.authoring import preferences, screeners, user_features
from algotrade_api.routes.drafting import screeners as screen_drafting
from algotrade_api.routes.preview import features as feature_check
from algotrade_api.routes.preview import screeners as screen_preview
from algotrade_api.routes.screens import run as screen_run

ROUTERS: tuple[APIRouter, ...] = (
    health.router,
    chains.router,
    user_features.router,
    feature_check.router,
    screen_run.router,
    screen_preview.router,
    screen_drafting.router,
    screeners.router,
    preferences.router,
)
