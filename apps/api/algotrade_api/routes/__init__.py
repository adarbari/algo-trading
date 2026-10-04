"""One router per area: parse parameters, call ONE explore query (or, under ``authoring/``,
one ``services.authoring`` write; ADR 0029), map it to a response schema. No business logic
here (ADR 0024); ``ROUTERS`` is what ``main.create_app`` mounts."""

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
from algotrade_api.routes.authoring import screeners, user_features

ROUTERS: tuple[APIRouter, ...] = (
    health.router,
    runs.router,
    universe.router,
    instruments.router,
    instruments.chains,
    explore.router,
    user_features.router,
    features.router,
    screens.router,
    screeners.router,
    backtests.router,
    configs.router,
    admin.router,
)
