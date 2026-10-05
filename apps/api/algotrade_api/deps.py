"""Request dependencies: the API settings, the read-only store, the live quotes (ADR 0028),
the config writer (ADR 0029: user configs only, through ``services.authoring``), the
on-request screen runner (ADR 0033), the user a
write is for, and the query parameters several routes share (comma-separated lists).

Settings come from the environment through ``algotrade.config.env`` (the one reader):
``ALGOTRADE_DATA_URL``, ``ALGOTRADE_CONFIG_DIR`` and ``ALGOTRADE_USER`` (a single local
user until identity arrives); ``ALGOTRADE_API_DEBUG=1`` serves the GraphiQL IDE. The store
is opened once per app and shared by every request.
"""

from dataclasses import dataclass, field
from typing import Annotated, cast

from fastapi import Depends, Query, Request

from algotrade.config.env import api_debug, config_dir, data_url, user_id
from algotrade.config.user import DEFAULT_USER, UserContext
from algotrade.core.model.errors import ConfigurationError
from algotrade.services.authoring.scope import ConfigWriter, open_writer
from algotrade.services.explore.store import ReadStore, open_store
from algotrade.services.live.quotes import LiveQuotes
from algotrade.services.ondemand.screens import OnDemandScreens

DEV_ORIGINS = (
    "http://localhost:5173",  # the web app's dev server (Vite)
    "http://127.0.0.1:5173",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
)


@dataclass(frozen=True)
class ApiSettings:
    data_url: str
    config_dir: str
    user: str = DEFAULT_USER
    cors_origins: tuple[str, ...] = field(default=DEV_ORIGINS)
    live: bool = False  # read live quotes from IB Gateway (the served app; off in tests)
    debug: bool = False  # serve the GraphiQL IDE at GET /graphql (local development only)

    @classmethod
    def from_env(cls) -> "ApiSettings":
        return cls(
            data_url(), str(config_dir()), user_id(DEFAULT_USER), live=True, debug=api_debug()
        )

    def open(self) -> ReadStore:
        return open_store(self.data_url, self.config_dir, UserContext(self.user))

    def open_writer(self) -> ConfigWriter:
        return open_writer(self.config_dir)


def get_store(request: Request) -> ReadStore:
    """The store ``create_app`` opened (read-only; shared by every request)."""
    return cast(ReadStore, request.app.state.store)


Store = Annotated[ReadStore, Depends(get_store)]


def get_writer(request: Request) -> ConfigWriter:
    """The config writer ``create_app`` opened (user configs only; ADR 0029)."""
    return cast(ConfigWriter, request.app.state.writer)


Writer = Annotated[ConfigWriter, Depends(get_writer)]


def write_user(
    store: Store,
    user: Annotated[
        str | None, Query(description="whose configs (a label until auth; default the API's)")
    ] = None,
) -> str:
    """``?user=`` (validated by ``services.authoring``), else the API's user."""
    return user if user is not None else store.user.user_id


User = Annotated[str, Depends(write_user)]


def get_live(request: Request) -> LiveQuotes:
    """The live quotes ``create_app`` set up (one IB Gateway session per app)."""
    return cast(LiveQuotes, request.app.state.live)


Live = Annotated[LiveQuotes, Depends(get_live)]


def get_ondemand(request: Request) -> OnDemandScreens:
    """The on-request screen runner ``create_app`` set up (ADR 0033); off in tests and the
    OpenAPI export unless one is given."""
    runner = cast(OnDemandScreens | None, request.app.state.ondemand)
    if runner is None:
        raise ConfigurationError("on-request runs are off in this app")
    return runner


OnDemand = Annotated[OnDemandScreens, Depends(get_ondemand)]


def name_list(value: str | None) -> list[str]:
    """``"a, b,,c"`` -> ``["a", "b", "c"]`` (comma-separated query values)."""
    return [v.strip() for v in (value or "").split(",") if v.strip()]
