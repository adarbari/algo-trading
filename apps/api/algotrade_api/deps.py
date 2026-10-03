"""Request dependencies: the API settings, the read-only store, the local user, and the
query parameters several routes share (universe filters, comma-separated lists).

Settings come from the environment through ``algotrade.config.env`` (the one reader):
``ALGOTRADE_DATA_URL``, ``ALGOTRADE_CONFIG_DIR`` and ``ALGOTRADE_USER`` (a single local
user until identity arrives). The store is opened once per app and shared by every request.
"""

from dataclasses import dataclass, field
from typing import Annotated, cast

from fastapi import Depends, Query, Request

from algotrade.config.env import config_dir, data_url, user_id
from algotrade.config.user import DEFAULT_USER, UserContext
from algotrade.services.explore.store import ReadStore, open_store
from algotrade.services.explore.universe import UniverseFilter

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

    @classmethod
    def from_env(cls) -> "ApiSettings":
        return cls(data_url(), str(config_dir()), user_id(DEFAULT_USER))

    def open(self) -> ReadStore:
        return open_store(self.data_url, self.config_dir, UserContext(self.user))


def get_store(request: Request) -> ReadStore:
    """The store ``create_app`` opened (read-only; shared by every request)."""
    return cast(ReadStore, request.app.state.store)


Store = Annotated[ReadStore, Depends(get_store)]


def universe_filter(
    security_type: str | None = None,
    leveraged: bool | None = None,
    sector: str | None = None,
    liquidity_class: str | None = None,
    q: Annotated[str | None, Query(description="symbol or company name contains")] = None,
    optionable: Annotated[bool | None, Query(description="has listed options")] = None,
) -> UniverseFilter:
    """The universe filters ``/universe`` and ``/explore/tickers`` share."""
    return UniverseFilter(security_type, leveraged, sector, liquidity_class, q, optionable)


Filters = Annotated[UniverseFilter, Depends(universe_filter)]


def name_list(value: str | None) -> list[str]:
    """``"a, b,,c"`` -> ``["a", "b", "c"]`` (comma-separated query values)."""
    return [v.strip() for v in (value or "").split(",") if v.strip()]
