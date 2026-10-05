import pytest

from algotrade.core.model.errors import ConfigurationError
from algotrade.services.explore.screens.table import screen_table
from algotrade.services.explore.store import NotFoundError, ReadStore
from algotrade_sources.framework.base import FixtureSource
from tests.helpers.api_store import END, PREVIOUS, api_store

CLOSE = "rollup.price_stats@v2.close"


@pytest.fixture(scope="module")
def store(golden_source: FixtureSource) -> ReadStore:
    return api_store(golden_source)[0]


def table(store: ReadStore, **kw: object):  # type: ignore[no-untyped-def]
    args = {"on": None, "decisions": [], "change": None, "q": None, "features": [], "sort": None}
    return screen_table(store, "vrp_scanner", **{**args, "page": 1, "size": 100, **kw})  # type: ignore[arg-type]


def test_rows_by_rank_with_criteria_columns_and_counts(store: ReadStore) -> None:
    found = table(store)
    assert (found.session, found.previous_session) == (END, PREVIOUS)
    assert found.decisions == {"QUALIFIED": 1, "WATCH": 1, "REJECT": 1}
    rows = found.page.items
    assert [(r.rank, r.symbol, r.decision) for r in rows] == [
        (1, "AAA", "QUALIFIED"),
        (2, "BBB", "WATCH"),
        (3, "CCC", "REJECT"),
    ]
    aaa, bbb, _ = rows
    assert aaa.flags == ["leveraged_inverse"]
    assert (aaa.criteria["iv30"].value, aaa.criteria["iv30"].outcome) == (0.62, "PASS")
    assert aaa.columns == {"spread": 0.05}
    assert (bbb.criteria["iv_rank"].outcome, bbb.reasons) == ("NEAR", "iv rank 40 < 50")
    assert [c.criterion_id for c in found.criteria][:3] == ["security_type", "status", "optionable"]
    assert found.column_names and found.feature_columns == []


def test_changes_against_the_previous_run(store: ReadStore) -> None:
    found = table(store)
    # AAA: REJECT then QUALIFIED (new); BBB: QUALIFIED then WATCH (still picked); CCC: dropped
    assert {r.symbol: (r.change, r.previous_decision) for r in found.page.items} == {
        "AAA": ("new", "REJECT"),
        "BBB": (None, "QUALIFIED"),
        "CCC": ("dropped", "QUALIFIED"),
    }
    assert found.changes == {"new": 1, "dropped": 1}
    assert [r.symbol for r in table(store, change="dropped").page.items] == ["CCC"]
    with pytest.raises(ConfigurationError):
        table(store, change="gone")


def test_filters_search_sort_and_page(store: ReadStore) -> None:
    only = table(store, decisions=["qualified", "watch"])
    assert [r.symbol for r in only.page.items] == ["AAA", "BBB"]
    assert only.decisions == table(store).decisions  # the counts ignore the filter
    assert [r.symbol for r in table(store, q="bb").page.items] == ["BBB"]
    assert [r.symbol for r in table(store, sort="-score").page.items] == ["BBB", "AAA", "CCC"]
    by_iv30 = table(store, sort="-criterion:iv30").page.items
    assert [r.symbol for r in by_iv30] == ["AAA", "BBB", "CCC"]  # rows without a value last
    second = table(store, page=2, size=2)
    assert (second.page.total, [r.symbol for r in second.page.items]) == (3, ["CCC"])
    with pytest.raises(ConfigurationError):
        table(store, sort="nope")


def test_catalogue_features_are_added_and_sortable(store: ReadStore) -> None:
    found = table(store, features=[CLOSE, CLOSE], sort=f"-{CLOSE}")
    assert found.feature_columns == [CLOSE]
    closes = {r.symbol: r.features[CLOSE] for r in found.page.items}
    assert set(closes) == {"AAA", "BBB", "CCC"}
    ranked = [r.features[CLOSE] for r in found.page.items if r.features[CLOSE] is not None]
    assert ranked == sorted(ranked, reverse=True)
    with pytest.raises(ConfigurationError):
        table(store, features=["feature.no_such"])


def test_not_found(store: ReadStore) -> None:
    for config in ("nope", "sma_trend", "short_premium_liquidity"):  # missing, strategy, python
        with pytest.raises(NotFoundError):
            screen_table(store, config, None, [], None, None, [], None, 1, 10)
    with pytest.raises(NotFoundError):
        table(store, on=PREVIOUS.replace(year=2021))
