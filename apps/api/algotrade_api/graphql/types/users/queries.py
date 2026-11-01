"""``UserQuery``: the root fields about the signed-in user (``viewer``, ``appearance``,
``traderPreferences``), a base of ``Query`` so the root stays under the file cap."""

import strawberry
from strawberry.types import Info

from algotrade.services.read.users.appearance import load_appearance
from algotrade.services.read.users.trader import load_trader_preferences
from algotrade.services.read.users.viewer import load_viewer
from algotrade_api.graphql.context import RequestContext
from algotrade_api.graphql.offload import INLINE
from algotrade_api.graphql.types.users.appearance import Appearance
from algotrade_api.graphql.types.users.trader_preferences import TraderPreferences
from algotrade_api.graphql.types.users.viewer import Viewer

Ctx = Info[RequestContext, None]


@strawberry.type
class UserQuery:
    @strawberry.field(  # type: ignore[untyped-decorator]
        description="Who this request is for: the signed-in registry user, their role and "
        "workspaces (ADR 0040; not session data)",
        metadata=INLINE,  # no I/O: never queues behind the page's reads
    )
    def viewer(self, info: Ctx) -> Viewer:
        return Viewer.of(load_viewer(info.context.viewer))

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="The theme the user chose (`light`, `dark` or `system`; ADR 0085): "
        "`system` when nothing valid is stored. Per user, not session data; not part of `viewer`, "
        "which has no I/O"
    )
    def appearance(self, info: Ctx) -> Appearance:
        ctx = info.context.stores()
        return (
            Appearance.of(load_appearance(ctx)) if ctx is not None else Appearance(theme="system")
        )

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="The user's default Ideas tab (`stocks` / `premium`; null until they "
        "answered the sign-up question) and watchlist (instrument ids; ADR 0083 amendment "
        "2026-11-01). Per user; the tickers come from the session's reference snapshot"
    )
    def trader_preferences(self, info: Ctx) -> TraderPreferences:
        ctx = info.context.read(None) or info.context.stores()
        return (
            TraderPreferences.of(load_trader_preferences(ctx))
            if ctx is not None
            else TraderPreferences(default_tab=None, watchlist=[])
        )
