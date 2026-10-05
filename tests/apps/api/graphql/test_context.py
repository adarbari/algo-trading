"""The request context: one read context (session resolved once, with dataloaders) per date
asked for in a request, and ``None`` for a store with nothing to resolve a session from."""

from datetime import date

from algotrade.services.read.context import NotFoundError, ReadContext, StoreContext
from algotrade_api.graphql.context import RequestContext, context_getter
from algotrade_api.graphql.loaders import Loaders


def test_one_read_context_per_date_per_request(ctx: ReadContext) -> None:
    opened: list[date | None] = []

    def opener(requested: date | None) -> ReadContext:
        opened.append(requested)
        return ctx

    request = RequestContext(opener)
    first = request.read(None)
    assert first is not None and isinstance(first.loaders, Loaders)
    assert request.read(None) is first
    request.read(date(2022, 11, 22))
    assert opened == [None, date(2022, 11, 22)]
    assert context_getter(opener)() is not context_getter(opener)()  # fresh per request


def test_nothing_stored_is_none() -> None:
    def opener(requested: date | None) -> ReadContext:
        raise NotFoundError("nothing stored")

    assert RequestContext(opener).read(None) is None


def test_the_session_free_context_opens_once_and_needs_no_session(ctx: ReadContext) -> None:
    def opener(requested: date | None) -> ReadContext:
        raise NotFoundError("nothing stored")

    stores = StoreContext(ctx.reader, ctx.configs, ctx.user, ctx.features, ctx.cache)
    opened: list[StoreContext] = []

    def open_stores() -> StoreContext:
        opened.append(stores)
        return stores

    request = RequestContext(opener, open_stores)
    assert request.stores() is stores and request.stores() is stores
    assert len(opened) == 1 and request.read(None) is None
    # Without a stores opener: the latest session's read context.
    assert RequestContext(lambda _: ctx).stores() is not None
    assert RequestContext(opener).stores() is None
