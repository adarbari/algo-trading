"""The request context: one read context (session resolved once, with dataloaders) per date
asked for in a request, and ``None`` for a store with nothing to resolve a session from."""

from datetime import date

from algotrade.services.read.context import NotFoundError, ReadContext
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
