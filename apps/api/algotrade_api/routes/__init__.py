"""One router per area: parse parameters, call ONE library function (under ``authoring/``, one
``services.authoring`` write, ADR 0029; under ``preview/``, one ``services.preview`` dry run of
unsaved input; else a job, the live quotes or the health check),
map it to a response schema. No business logic here (ADR 0024). ``main.create_app`` mounts
``PUBLIC_ROUTERS`` as they are and every one of ``ROUTERS`` behind the caller dependency
(``deps.get_caller``, ADR 0040)."""

from fastapi import APIRouter

from algotrade_api.routes import chains, health
from algotrade_api.routes.authoring import preferences, screeners, user_features
from algotrade_api.routes.drafting import screeners as screen_drafting
from algotrade_api.routes.preview import features as feature_check
from algotrade_api.routes.preview import screeners as screen_preview
from algotrade_api.routes.screens import run as screen_run

PUBLIC_ROUTERS: tuple[APIRouter, ...] = (health.router,)  # answers without credentials
ROUTERS: tuple[APIRouter, ...] = (
    chains.router,
    user_features.router,
    feature_check.router,
    screen_run.router,
    screen_preview.router,
    screen_drafting.router,
    screeners.router,
    preferences.router,
)
