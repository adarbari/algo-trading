"""The admin-only reads of the ``Query`` root that are not about a session, in their own class
so ``types/query.py`` stays under the file-length cap: ``Query`` inherits them, and the schema
is the same as if they were declared there. Each is ``AdminOnly`` (ADR 0040)."""

import strawberry
from strawberry.types import Info

from algotrade.services.read.event_scope.event_scope import load_event_scope
from algotrade.services.read.users.registry import load_user_registry
from algotrade.services.read.users.viewer import load_viewer
from algotrade_api.graphql.context import RequestContext
from algotrade_api.graphql.offload import off_loop
from algotrade_api.graphql.permissions import AdminOnly
from algotrade_api.graphql.types.ops.event_scope import EventScope
from algotrade_api.graphql.types.query_args import Day
from algotrade_api.graphql.types.users.registry import UserRegistry


@strawberry.type
class AdminReads:
    @strawberry.field(  # type: ignore[untyped-decorator]
        description="The people the site declares (id, name, role, held data licences; never an "
        "email), in declaration order, for the Admin Users page",
        extensions=[AdminOnly()],
    )
    async def user_registry(self, info: Info[RequestContext, None]) -> UserRegistry | None:
        ctx = await info.context.astores()
        viewer = load_viewer(info.context.viewer)
        found = await off_loop(load_user_registry, ctx, viewer) if ctx is not None else None
        return UserRegistry.of(found) if found is not None else None

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="The event-study scope list for the session (the site file plus the admin's "
        "additions minus removals): each name with its reasons and source, last deep-dive review "
        "(stale after 90 days), the share of its biggest moves attributed and the macro "
        "calendar's reach (ADR 0050, plan 5.5). Null: nothing stored",
        extensions=[AdminOnly()],
    )
    async def event_scope(
        self, info: Info[RequestContext, None], date: Day = None
    ) -> EventScope | None:
        ctx = await info.context.aread(date)
        found = await off_loop(load_event_scope, ctx) if ctx is not None else None
        return EventScope.of(found) if found is not None else None
