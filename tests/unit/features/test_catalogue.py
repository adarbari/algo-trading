"""The feature registry's metadata lookups and the generated catalogue's rendering."""

from dataclasses import replace

from algotrade.features.catalogue import _cell, render, valid_values
from algotrade.features.registry import FEATURES, GROUPS, catalogue_columns, feature
from tests.helpers.rollup_store import features


def test_lookup_by_key_or_selection_field() -> None:
    hv = feature("price_stats.hv30@v1")
    assert hv is not None and hv.unit == "decimal" and hv.valid_range == (0, 5)
    assert feature("rollup.price_stats@v1.hv30") is hv
    assert feature("instrument.sector") is None and feature("nope.x@v1") is None
    assert catalogue_columns()["price_stats@v1"]["hv30"] == "float"


def test_valid_values_and_cells() -> None:
    plain = features({"a": "float"})[0]
    assert valid_values(plain) == ""
    assert valid_values(replace(plain, valid_range=(None, 0))) == "<= 0"
    assert valid_values(replace(plain, valid_range=(None, None))) == ""
    assert valid_values(FEATURES["price_stats.hv30@v1"]) == "0 .. 5"
    assert valid_values(FEATURES["price_stats.ret_20d@v1"]) == ">= -1"
    assert valid_values(FEATURES["iv_history.rank_status@v1"]) == "UNKNOWN, PROVISIONAL, FULL"
    assert _cell("a | b\nc") == "a \\| b c"


def test_render_lists_every_group_and_feature() -> None:
    text = render()
    for key in GROUPS:
        assert f"## `{key}`" in text
    assert f"{len(FEATURES)} features in {len(GROUPS)} groups" in text
    assert "| `hv30` | window | float | decimal | 0 .. 5 |" in text
