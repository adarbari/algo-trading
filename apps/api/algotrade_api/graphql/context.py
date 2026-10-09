"""The context of one GraphQL request (ADR 0037): ``RequestContext.read(date)`` is the
``ReadContext`` for the session ``date`` resolves to (``services.read.context.open_context``,
through the opener ``create_app`` gives the router), opened once per date per request, as the
request's caller, and carrying that request's dataloaders (``loaders.Loaders``).
``RequestContext.viewer`` is the caller: the registry user ``deps.get_caller`` resolved for
this request (ADR 0040; the same resolution the route's guard made, cached by FastAPI).

A top-level field takes the session as its ``date`` argument and hands the ``ReadContext`` to
the objects it returns; fields of one operation that pass the same ``date`` share one
resolved session and one set of dataloaders. An empty store (nothing to resolve a session
from) is ``None``: the fields are null, not an error (ADR 0036)."""

import threading
from collections.abc import Callable
from dataclasses import replace
from datetime import date

from fastapi import Request
from strawberry.dataloader import DataLoader
from strawberry.fastapi import BaseContext

from algotrade.config.site.users import UserRecord
from algotrade.config.user import UserContext
from algotrade.services.read.availability.cause import Cause
from algotrade.services.read.availability.explain import explain
from algotrade.services.read.context import NotFoundError, ReadContext, Stores
from algotrade_api.deps import Caller
from algotrade_api.graphql.loaders import Loaders
from algotrade_api.graphql.offload import off_loop

# Opens the read context for a user and a requested session (None: the latest):
# ``open_context`` over the app's store, configs and result cache.
Opener = Callable[[UserContext, date | None], ReadContext]
# Opens a user's session-free context (configs, run records, the catalogue): ``open_stores``.
StoresOpener = Callable[[UserContext], Stores]


class RequestContext(BaseContext):
    """What a resolver reads through (``info.context``) during one request: every read is
    for ``viewer``, the request's caller."""

    def __init__(
        self, opener: Opener, viewer: UserRecord, stores: StoresOpener | None = None
    ) -> None:
        super().__init__()
        self.viewer = viewer
        self._user = UserContext(viewer.user_id)
        self._open = opener
        self._open_stores = stores
        # top-level fields resolve in the read pool, side by side: opening is under a lock
        self._lock = threading.RLock()
        self._contexts: dict[date | None, ReadContext | None] = {}
        self._stores: Stores | None = None
        self._causes: DataLoader[Cause, Cause] = DataLoader(load_fn=self._explain_all)

    async def _explain_all(self, leaves: list[Cause]) -> list[Cause]:
        """``explain`` of each distinct leaf: one read of the run records each, off the loop."""
        stores = await self.astores()
        if stores is None:
            return leaves
        return [await off_loop(explain, stores, leaf) for leaf in leaves]

    async def cause_of(self, leaf: Cause) -> Cause:
        """The chain behind ``leaf`` (ADR 0056): batched and cached per request, and called
        only behind ``AdminCause``, so a trader's request never reads a run record for it."""
        return await self._causes.load(leaf)

    def read(self, requested: date | None) -> ReadContext | None:
        """The read context for ``requested`` (None: the latest session), with this request's
        dataloaders; ``None`` when the store holds nothing to resolve a session from."""
        with self._lock:
            if requested not in self._contexts:
                try:
                    ctx = self._open(self._user, requested)
                except NotFoundError:
                    self._contexts[requested] = None
                else:
                    self._contexts[requested] = replace(ctx, loaders=Loaders(ctx))
            return self._contexts[requested]

    async def aread(self, requested: date | None) -> ReadContext | None:
        """``read`` for an async resolver: opening a context lists partitions (parquet
        directories), so it runs off the event loop."""
        return await off_loop(self.read, requested)

    async def astores(self) -> Stores | None:
        """``stores`` for an async resolver, off the event loop."""
        return await off_loop(self.stores)

    def stores_for(self, user_id: str | None) -> Stores | None:
        """``stores`` for another user (an admin acting for them, ADR 0040): the caller's own
        context when it is theirs. Only behind ``AdminOnly``; never cached across users."""
        if user_id is None or user_id == self.viewer.user_id:
            return self.stores()
        if self._open_stores is None:
            ctx = self._open(UserContext(user_id), None)
            return ctx
        return self._open_stores(UserContext(user_id))

    def stores(self) -> Stores | None:
        """The session-free context for configs, run records and the catalogue: it needs no
        stored market data (a fresh store still lists its configs). Without a stores opener,
        the latest session's read context (None on an empty store)."""
        if self._open_stores is None:
            return self.read(None)
        with self._lock:
            if self._stores is None:
                self._stores = self._open_stores(self._user)
            return self._stores


def context_getter(
    opener: Opener, stores: StoresOpener | None = None
) -> Callable[[UserRecord, Request], RequestContext]:
    """The router's ``context_getter``: a fresh ``RequestContext`` per request, for the caller
    (a FastAPI dependency: Strawberry resolves it, sharing the request's one resolution)."""

    def get_context(caller: Caller, request: Request) -> RequestContext:
        request.state.viewer = caller  # ``errors.response_of`` words an error by the role
        return RequestContext(opener, caller, stores)

    return get_context
