from pathlib import Path

import pytest

from algotrade.data import StoreReader
from algotrade.services.read.context import ReadContext
from algotrade.services.read.screens.views import (
    NamedView,
    TableView,
    load_view,
    scope_parts,
    surface_exists,
)
from algotrade.storage.configs.files import FileConfigStore
from tests.unit.services.read.screens.conftest import context

PREFS = {
    ("me", "preferences", "preferences"): {
        "views": {
            "screener:alpha": {
                "view": {"columns": ["rollup.iv30@v1.iv30"], "sort": "-score",
                         "decisions": ["QUALIFIED"],
                         "narrow_columns": ["name", "criterion:a"]},
                "views": {"Earnings": {"columns": ["feature.earnings_before_expiry"]}},
            }
        }
    }
}  # fmt: skip


def test_the_default_and_a_named_view(reader: StoreReader) -> None:
    ctx = context(reader, PREFS)
    assert load_view(ctx, "screener:alpha") == TableView(
        "screener:alpha", None, True, ("rollup.iv30@v1.iv30",), "-score", ("QUALIFIED",),
        ("Earnings",), ("name", "criterion:a"), "", (NamedView("Earnings"),),
    )  # fmt: skip
    named = load_view(ctx, "screener:alpha", "Earnings")
    assert named is not None
    assert (named.saved, named.columns, named.sort) == (
        True, ("feature.earnings_before_expiry",), None
    )  # fmt: skip
    assert named.narrow_columns == ()  # a document without the key


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


def test_a_surface_with_a_filter_bar_has_views_and_one_without_has_none(
    reader: StoreReader,
) -> None:
    saved = {("me", "preferences", "preferences"): {
        "views": {"surface:ideas": {"view": {"columns": [], "filters": "decision:QUALIFIED"}}},
    }}  # fmt: skip
    ctx = context(reader, saved)
    found = load_view(ctx, "surface:ideas")
    assert found is not None and (found.saved, found.filters) == (True, "decision:QUALIFIED")
    assert load_view(ctx, "surface:no_such_surface") is None
    assert scope_parts("surface:edge_trades") == ("surface", "edge_trades")


def test_a_surface_id_no_file_could_have_is_no_view_not_an_error(tmp_path: Path) -> None:
    """A store that checks ids (the file store) refuses ``Bad!``; the read answers no view."""
    assert surface_exists(FileConfigStore(tmp_path), "Bad!") is False
    assert surface_exists(FileConfigStore(tmp_path), "ideas") is False  # no such file here
