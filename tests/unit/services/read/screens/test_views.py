from algotrade.data import StoreReader
from algotrade.services.read.context import ReadContext
from algotrade.services.read.screens.views import TableView, load_view
from tests.unit.services.read.screens.conftest import context

PREFS = {
    ("me", "preferences", "preferences"): {
        "screeners": {
            "alpha": {
                "view": {"columns": ["rollup.iv30@v1.iv30"], "sort": "-score",
                         "decisions": ["QUALIFIED"]},
                "views": {"Earnings": {"columns": ["feature.earnings_before_expiry"]}},
            }
        }
    }
}  # fmt: skip


def test_the_default_and_a_named_view(reader: StoreReader) -> None:
    ctx = context(reader, PREFS)
    assert load_view(ctx, "alpha") == TableView(
        "alpha", None, True, ("rollup.iv30@v1.iv30",), "-score", ("QUALIFIED",), ("Earnings",)
    )
    named = load_view(ctx, "alpha", "Earnings")
    assert named is not None
    assert (named.saved, named.columns, named.sort) == (
        True, ("feature.earnings_before_expiry",), None
    )  # fmt: skip


def test_nothing_saved_is_an_empty_view_not_an_error(ctx: ReadContext) -> None:
    assert load_view(ctx, "beta") == TableView("beta", None, False, (), None, (), ())
    assert load_view(ctx, "beta", "missing") == TableView(
        "beta", "missing", False, (), None, (), ()
    )


def test_a_screener_the_user_does_not_see(ctx: ReadContext) -> None:
    assert load_view(ctx, "nope") is None
