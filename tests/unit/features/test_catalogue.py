"""The feature registry's metadata lookups and the generated catalogue's rendering."""

from dataclasses import replace

from algotrade.features.catalogue import _cell, render, valid_values
from algotrade.features.registry import FEATURES, GROUPS, catalogue_columns, feature
from algotrade.features.site import site_features
from algotrade.storage.configs.files import FileConfigStore
from tests.conftest import REPO_ROOT
from tests.helpers.rollup_store import features


def test_lookup_by_key_or_selection_field() -> None:
    hv = feature("price_stats.hv30@v2")
    assert hv is not None and hv.unit == "decimal" and hv.valid_range == (0, 5)
    assert feature("rollup.price_stats@v2.hv30") is hv
    assert feature("instrument.sector") is None and feature("nope.x@v1") is None
    assert catalogue_columns()["price_stats@v2"]["hv30"] == "float32"


def test_valid_values_and_cells() -> None:
    plain = features({"a": "float"})[0]
    assert valid_values(plain) == ""
    assert valid_values(replace(plain, valid_range=(None, 0))) == "<= 0"
    assert valid_values(replace(plain, valid_range=(None, None))) == ""
    assert valid_values(FEATURES["price_stats.hv30@v2"]) == "0 .. 5"
    assert valid_values(FEATURES["price_stats.ret_20d@v2"]) == ">= -1"
    assert valid_values(FEATURES["iv_history.rank_status@v2"]) == "UNKNOWN, PROVISIONAL, FULL"
    assert _cell("a | b\nc") == "a \\| b c"


def test_render_lists_every_group_feature_expression_and_superseded_group() -> None:
    fs = site_features(FileConfigStore(REPO_ROOT / "config"))
    text = render(fs)
    for key in GROUPS:
        assert f"## `{key}`" in text
    stored = sum(len(g.features) for g in GROUPS.values())
    assert f"{stored} stored features in {len(GROUPS)} groups" in text
    assert f"{len(fs.expressions)} expression features" in text
    assert "| `hv30` | window | float32 | decimal | open | 0 .. 5 |" in text
    assert "| `iv_rank_252d_ibkr` | window | float32 | decimal | personal | 0 .. 1 |" in text
    assert "| `iv_rank_source` | label | str | category | personal | ibkr, ours |" in text
    assert "### `liquidity.toml`" in text and "| `near_52w` | label | str |" in text
    assert "`rollups/instrument/div_yield@v1` |" in text and "(within = 0.1)" in text
    assert "| `liquidity_class@v1` | `price_stats@v2` + expression features; `chain_oi`" in text
    assert "`rule_hash` retired" in text
