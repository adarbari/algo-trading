"""The Edges list (ADR 0082, surface ``edges``): the search matches id, name and thesis, the old
views are filters (mine / following / rejected), and a figure the verdict does not hold never
passes a filter on it."""

import tomllib

import pytest

from algotrade.services.read.context import ReadContext
from algotrade.services.read.filtering.definitions import FilterRefusedError
from algotrade.services.read.filtering.masks import FilterInput
from algotrade.services.read.lists.edges import EdgeList, load_edge_list
from tests.conftest import REPO_ROOT
from tests.unit.services.read.edge_desk.conftest import backend, context  # noqa: F401  (fixture)
from tests.unit.services.read.evaluation.conftest import EDGE

SHIPPED = tomllib.loads((REPO_ROOT / "config/site/filters/edges.toml").read_text())
OTHER = {
    **EDGE, "id": "other", "name": "Quiet Zebra", "status": "rejected",
    "thesis": "Striped names mean revert.", "rejection_reason": "no edge",
}  # fmt: skip
EXTRA = {("site", "filters", "edges"): SHIPPED, ("site", "edges", "other"): OTHER}


@pytest.fixture
def ctx(backend) -> ReadContext:  # noqa: F811
    return context(backend, extra=EXTRA)


def ids(found: EdgeList) -> list[str]:
    return [r.edge.id for r in found.items]


def test_no_filters_is_every_edge(ctx: ReadContext) -> None:
    found = load_edge_list(ctx)
    assert ids(found) == ["drift", "other"]
    assert found.total == found.facets.total == 2


def test_search_matches_name_thesis_and_id(ctx: ReadContext) -> None:
    assert ids(load_edge_list(ctx, q="zebra")) == ["other"]  # the name
    assert ids(load_edge_list(ctx, q="  RISING ")) == ["drift"]  # the thesis, any case, trimmed
    assert ids(load_edge_list(ctx, q="oth")) == ["other"]  # the id
    assert load_edge_list(ctx, q="nothing like it").total == 0


def test_the_views_are_filters(ctx: ReadContext) -> None:
    rejected = load_edge_list(ctx, [FilterInput("status", values=["rejected"])])
    assert ids(rejected) == ["other"]  # view "rejected"
    following = load_edge_list(ctx, [FilterInput("followed", values=["yes"])])
    assert ids(following) == ["drift"]  # view "following": the user follows the site edge
    assert ids(load_edge_list(ctx, [FilterInput("mine", values=["yes"])])) == []


def test_the_search_narrows_before_the_facets(ctx: ReadContext) -> None:
    found = load_edge_list(ctx, [FilterInput("status", values=["rejected"])], q="names")
    assert found.facets.total == 2 and ids(found) == ["other"]  # both theses say "names"


def test_a_figure_the_verdict_lacks_never_passes(ctx: ReadContext) -> None:
    every = load_edge_list(ctx, [FilterInput("sample", min=0)])
    held = {r.edge.id for r in load_edge_list(ctx).items if r.summary.oos_trades is not None}
    assert set(ids(every)) == held  # a min of 0 admits no null
    sample = next(f for f in every.facets.items if f.id == "sample")
    assert sample.unknown == 2 - len(held)


def test_a_live_state_is_picked_by_its_word(ctx: ReadContext) -> None:
    found = load_edge_list(ctx, [FilterInput("live_state", values=["not_recording"])])
    assert "other" in ids(found)  # a rejected edge records no paper trades


def test_a_filter_that_is_not_offered_is_refused(ctx: ReadContext) -> None:
    with pytest.raises(FilterRefusedError):
        load_edge_list(
            ctx, [FilterInput("hit_rate", min=0.5)]
        )  # dropped: not stored in the headline
