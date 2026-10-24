"""The request context: one read context (session resolved once, with dataloaders) per date
asked for in a request, as the request's caller, and ``None`` for a store with nothing to
resolve a session from."""

from datetime import date
from types import SimpleNamespace

import pytest
from fastapi import Request
from graphql import FragmentDefinitionNode, OperationDefinitionNode, parse

from algotrade.config.site.users import Role, UserRecord
from algotrade.config.user import UserContext
from algotrade.services.read.context import NotFoundError, ReadContext, StoreContext
from algotrade_api.graphql.context import RequestContext, context_getter, selects
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
    get = context_getter(opener)
    asked = Request({"type": "http", "headers": []})
    assert get(ANA, asked) is not get(ANA, asked)  # fresh per request
    assert asked.state.viewer == ANA  # the error words read the role from here


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


def info_of(query: str) -> SimpleNamespace:
    doc = parse(query)
    ops = [d for d in doc.definitions if isinstance(d, OperationDefinitionNode)]
    fragments = {d.name.value: d for d in doc.definitions if isinstance(d, FragmentDefinitionNode)}
    (top,) = ops[0].selection_set.selections
    return SimpleNamespace(_raw_info=SimpleNamespace(field_nodes=[top], fragments=fragments))


@pytest.mark.parametrize(
    ("query", "wanted"),
    [
        ("{ page { facets { total } rows { id } } }", True),
        ("{ page { ... on Page { facets { total } } } }", True),
        ("{ page { ...F } } fragment F on Page { facets { total } }", True),
        (
            "{ page { ...A } } fragment A on Page { ...B } fragment B on Page { facets { total } }",
            True,
        ),
        ("{ page { rows { facets } } }", False),  # a deeper field of the same name is not it
        ("{ page { total } }", False),
    ],
)
def test_a_field_is_selected_directly_or_through_a_fragment(query: str, wanted: bool) -> None:
    assert selects(info_of(query), "facets") is wanted
