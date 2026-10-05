"""The context of one GraphQL request (ADR 0037): ``RequestContext.read(date)`` is the
``ReadContext`` for the session ``date`` resolves to (``services.read.context.open_context``,
through the opener ``create_app`` gives the router), opened once per date per request and
carrying that request's dataloaders (``loaders.Loaders``).

A top-level field takes the session as its ``date`` argument and hands the ``ReadContext`` to
the objects it returns; fields of one operation that pass the same ``date`` share one
resolved session and one set of dataloaders. An empty store (nothing to resolve a session
from) is ``None``: the fields are null, not an error (ADR 0036)."""

from collections.abc import Callable
from dataclasses import replace
from datetime import date

from strawberry.fastapi import BaseContext

from algotrade.services.read.context import NotFoundError, ReadContext, Stores
from algotrade_api.graphql.loaders import Loaders

# Opens the read context for a requested session (None: the latest): ``open_context`` over
# the app's store, configs, user and result cache.
Opener = Callable[[date | None], ReadContext]
# Opens the session-free context (configs, run records, the catalogue): ``open_stores``.
StoresOpener = Callable[[], Stores]


class RequestContext(BaseContext):
    """What a resolver reads through (``info.context``) during one request."""

    def __init__(self, opener: Opener, stores: StoresOpener | None = None) -> None:
        super().__init__()
        self._open = opener
        self._open_stores = stores
        self._contexts: dict[date | None, ReadContext | None] = {}
        self._stores: Stores | None = None

    def read(self, requested: date | None) -> ReadContext | None:
        """The read context for ``requested`` (None: the latest session), with this request's
        dataloaders; ``None`` when the store holds nothing to resolve a session from."""
        if requested not in self._contexts:
            try:
                ctx = self._open(requested)
            except NotFoundError:
                self._contexts[requested] = None
            else:
                self._contexts[requested] = replace(ctx, loaders=Loaders(ctx))
        return self._contexts[requested]

    def stores(self) -> Stores | None:
        """The session-free context for configs, run records and the catalogue: it needs no
        stored market data (a fresh store still lists its configs). Without a stores opener,
        the latest session's read context (None on an empty store)."""
        if self._open_stores is None:
            return self.read(None)
        if self._stores is None:
            self._stores = self._open_stores()
        return self._stores


def context_getter(
    opener: Opener, stores: StoresOpener | None = None
) -> Callable[[], RequestContext]:
    """The router's ``context_getter``: a fresh ``RequestContext`` per request."""

    def get_context() -> RequestContext:
        return RequestContext(opener, stores)

    return get_context
