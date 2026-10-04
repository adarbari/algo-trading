"""One router per area: parse parameters, call ONE explore query (or, under ``authoring/``,
one ``services.authoring`` write; ADR 0029; under ``preview/``, one dry run of unsaved input),
map it to a response schema. No business logic here (ADR 0024); ``ROUTERS`` is what
``main.create_app`` mounts."""

from fastapi import APIRouter

from algotrade_api.routes import (
    admin,
    backtests,
    configs,
    explore,
    features,
    health,
    instruments,
    runs,
    screens,
    universe,
)
from algotrade_api.routes.authoring import preferences, screeners, user_features
from algotrade_api.routes.preview import features as feature_check
from algotrade_api.routes.preview import screeners as screen_preview

ROUTERS: tuple[APIRouter, ...] = (
    health.router,
    runs.router,
    universe.router,
    instruments.router,
    instruments.chains,
    explore.router,
    user_features.router,
    feature_check.router,
    features.router,
    screens.router,
    screen_preview.router,
    screeners.router,
    preferences.router,
    screens.ideas_router,
    backtests.router,
    configs.router,
    admin.router,
)
