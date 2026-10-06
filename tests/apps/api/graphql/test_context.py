"""The request context: one read context (session resolved once, with dataloaders) per date
asked for in a request, as the request's caller, and ``None`` for a store with nothing to
resolve a session from."""

from datetime import date

from algotrade.config.site.users import Role, UserRecord
from algotrade.config.user import UserContext
from algotrade.services.read.context import NotFoundError, ReadContext, StoreContext
from algotrade_api.graphql.context import RequestContext, context_getter
from algotrade_api.graphql.loaders import Loaders

ANA = UserRecord("ana", Role.ADMIN)


def test_one_read_context_per_date_per_request(ctx: ReadContext) -> None:
    opened: list[tuple[str, date | None]] = []

    def opener(user: UserContext, requested: date | None) -> ReadContext:
        opened.append((user.user_id, requested))
        return ctx

    request = RequestContext(opener, ANA)
    first = request.read(None)
    assert first is not None and isinstance(first.loaders, Loaders)
    assert request.read(None) is first and request.viewer == ANA
    request.read(date(2022, 11, 22))
    assert opened == [("ana", None), ("ana", date(2022, 11, 22))]  # always as the caller
    assert context_getter(opener)(ANA) is not context_getter(opener)(ANA)  # fresh per request


def test_nothing_stored_is_none() -> None:
    def opener(user: UserContext, requested: date | None) -> ReadContext:
        raise NotFoundError("nothing stored")

    assert RequestContext(opener, ANA).read(None) is None


def test_the_session_free_context_opens_once_and_needs_no_session(ctx: ReadContext) -> None:
    def opener(user: UserContext, requested: date | None) -> ReadContext:
        raise NotFoundError("nothing stored")

    stores = StoreContext(ctx.reader, ctx.configs, ctx.user, ctx.features, ctx.cache)
    opened: list[str] = []

    def open_stores(user: UserContext) -> StoreContext:
        opened.append(user.user_id)
        return stores

    request = RequestContext(opener, ANA, open_stores)
    assert request.stores() is stores and request.stores() is stores
    assert opened == ["ana"] and request.read(None) is None
    # Without a stores opener: the latest session's read context.
    assert RequestContext(lambda _u, _d: ctx, ANA).stores() is not None
    assert RequestContext(opener, ANA).stores() is None
