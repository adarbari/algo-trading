"""The Screeners list (ADR 0082, surface ``screeners``): the search matches id, name and
description, the shipped filters narrow it through the one pass (a screener with no run never
passes a filter on its run), and with no filters it is ``load_screeners`` unchanged."""

import tomllib

import pytest

from algotrade.services.read.context import ReadContext
from algotrade.services.read.filtering.definitions import FilterRefusedError
from algotrade.services.read.filtering.masks import FilterInput
from algotrade.services.read.lists.screeners import load_screener_list
from algotrade.services.read.screens.screeners import load_screeners
from tests.conftest import REPO_ROOT
from tests.unit.services.read.screens.conftest import (  # noqa: F401  (fixtures)
    CONFIGS,
    backend,
    context,
    reader,
)

SHIPPED = tomllib.loads((REPO_ROOT / "config/site/filters/screeners.toml").read_text())
DOCS = {("site", "filters", "screeners"): SHIPPED}


@pytest.fixture
def ctx(reader) -> ReadContext:  # noqa: F811
    return context(reader, DOCS)


def ids(found) -> list[str]:
    return [r.screener.id for r in found.items]


def test_no_filters_is_the_whole_list(ctx: ReadContext) -> None:
    found = load_screener_list(ctx)
    assert ids(found) == [s.id for s in load_screeners(ctx)] == ["alpha", "beta", "gamma"]
    assert found.total == found.facets.total == 3


def test_owner_is_mine_or_site(ctx: ReadContext) -> None:
    owners = {r.screener.id: r.owner for r in load_screener_list(ctx).items}
    assert owners == {"alpha": "site", "beta": "mine", "gamma": "mine"}
    mine = load_screener_list(ctx, [FilterInput("owner", values=["mine"])])
    assert ids(mine) == ["beta", "gamma"]


def test_search_matches_the_name_not_only_the_id(ctx: ReadContext) -> None:
    assert ids(load_screener_list(ctx, q="my b")) == ["beta"]  # the name "My beta"
    assert ids(load_screener_list(ctx, q="  ALPHA ")) == ["alpha"]  # any case, trimmed
    assert ids(load_screener_list(ctx, q="gam")) == ["gamma"]  # the id (its name)
    assert load_screener_list(ctx, q="zzz").total == 0


def test_search_matches_the_description(reader) -> None:  # noqa: F811
    doc = dict(CONFIGS[("site", "screeners", "alpha@1")], description="finds dip buys")
    ctx = context(reader, {**DOCS, ("site", "screeners", "alpha@1"): doc})
    assert ids(load_screener_list(ctx, q="DIP")) == ["alpha"]


def test_the_search_narrows_before_the_facets(ctx: ReadContext) -> None:
    found = load_screener_list(ctx, [FilterInput("owner", values=["site"])], q="a")
    assert found.facets.total == 3  # alpha, beta ("My beta"), gamma contain an "a"
    assert ids(found) == ["alpha"] and found.total == found.facets.matched == 1


def test_unknown_never_passes_a_range_with_a_min_of_zero(ctx: ReadContext) -> None:
    # gamma never ran for the session: its picked count is unknown, not 0
    found = load_screener_list(ctx, [FilterInput("picked", min=0)])
    ran = {r.screener.id for r in load_screener_list(ctx).items if r.latest_run is not None}
    assert set(ids(found)) == ran and "gamma" not in ran
    picked = next(f for f in found.facets.items if f.id == "picked")
    assert picked.unknown == 1


def test_a_screener_with_no_run_has_no_run_status(ctx: ReadContext) -> None:
    found = load_screener_list(ctx, [FilterInput("run_status", values=["COMPLETE"])])
    assert "gamma" not in ids(found)


def test_a_filter_that_is_not_offered_is_refused(ctx: ReadContext) -> None:
    with pytest.raises(FilterRefusedError):
        load_screener_list(ctx, [FilterInput("nope", values=["x"])])


def test_a_switched_off_filter_removes_nothing(ctx: ReadContext) -> None:
    off = load_screener_list(ctx, [FilterInput("owner", values=["site"], active=False)])
    assert off.total == 3
