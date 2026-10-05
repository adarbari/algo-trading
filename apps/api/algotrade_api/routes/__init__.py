"""One router per area: parse parameters, call ONE explore query (or, under ``authoring/``,
one ``services.authoring`` write; ADR 0029; under ``preview/``, one dry run of unsaved input),
map it to a response schema. No business logic here (ADR 0024); ``ROUTERS`` is what
``main.create_app`` mounts."""

from fastapi import APIRouter

from algotrade_api.routes import admin, chains, health, runs
from algotrade_api.routes.authoring import preferences, screeners, user_features
from algotrade_api.routes.preview import features as feature_check
from algotrade_api.routes.preview import screeners as screen_preview
from algotrade_api.routes.screens import run as screen_run

ROUTERS: tuple[APIRouter, ...] = (
    health.router,
    runs.router,
    chains.router,
    user_features.router,
    feature_check.router,
    screen_run.router,
    screen_preview.router,
    screeners.router,
    preferences.router,
    admin.router,
)
