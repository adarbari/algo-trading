"""One router per area: parse parameters, call ONE explore query, map it to a response
schema. No business logic here (ADR 0024); ``ROUTERS`` is what ``main.create_app`` mounts."""

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

ROUTERS: tuple[APIRouter, ...] = (
    health.router,
    runs.router,
    universe.router,
    instruments.router,
    instruments.chains,
    explore.router,
    features.router,
    screens.router,
    backtests.router,
    configs.router,
    admin.router,
)
