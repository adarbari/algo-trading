import pytest

from algotrade.data import StoreReader
from algotrade.services.read.context import ReadContext
from algotrade.services.read.screens.views import TableView, load_view, scope_parts
from tests.unit.services.read.screens.conftest import context

PREFS = {
    ("me", "preferences", "preferences"): {
        "views": {
            "screener:alpha": {
                "view": {"columns": ["rollup.iv30@v1.iv30"], "sort": "-score",
                         "decisions": ["QUALIFIED"]},
                "views": {"Earnings": {"columns": ["feature.earnings_before_expiry"]}},
            }
        }
    }
}  # fmt: skip


def test_the_default_and_a_named_view(reader: StoreReader) -> None:
    ctx = context(reader, PREFS)
    assert load_view(ctx, "screener:alpha") == TableView(
        "screener:alpha", None, True, ("rollup.iv30@v1.iv30",), "-score", ("QUALIFIED",),
        ("Earnings",),
    )  # fmt: skip
    named = load_view(ctx, "screener:alpha", "Earnings")
    assert named is not None
    assert (named.saved, named.columns, named.sort) == (
        True, ("feature.earnings_before_expiry",), None
    )  # fmt: skip


def test_a_view_saved_before_views_were_scoped_is_still_read(reader: StoreReader) -> None:
    legacy = {("me", "preferences", "preferences"): {
        "screeners": {"alpha": {"view": {"columns": ["feature.x"], "decisions": []}}},
    }}  # fmt: skip
    found = load_view(context(reader, legacy), "screener:alpha")
    assert found is not None and (found.saved, found.columns) == (True, ("feature.x",))


def test_nothing_saved_is_an_empty_view_not_an_error(ctx: ReadContext) -> None:
    assert load_view(ctx, "screener:beta") == TableView(
        "screener:beta", None, False, (), None, (), ()
    )
    assert load_view(ctx, "screener:beta", "missing") == TableView(
        "screener:beta", "missing", False, (), None, (), ()
    )


def test_a_screener_the_user_does_not_see_or_an_unknown_scope(ctx: ReadContext) -> None:
    assert load_view(ctx, "screener:nope") is None
    assert load_view(ctx, "alpha") is None  # no kind
    assert load_view(ctx, "explore:alpha") is None  # not a kind of table


def test_scope_parts() -> None:
    assert scope_parts("screener:vrp_scanner") == ("screener", "vrp_scanner")
    for bad in ("screener:", "vrp_scanner", "other:x"):
        with pytest.raises(ValueError, match="view scope"):
            scope_parts(bad)
