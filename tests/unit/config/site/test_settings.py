"""The one site-settings loader (``config/site/settings.py``): typed objects from every
``config/site/*.toml``, defaults for what is missing, and errors that name the file, section
and key for anything unknown, mistyped or out of range."""

import tomllib
from typing import Any

import pytest

from algotrade.config.site.settings import (
    BacktestSettings,
    NightlySettings,
    ScreeningSettings,
    SourcesSettings,
    UniverseSettings,
    load_nightly,
    load_sources,
    load_universe,
)
from algotrade.core.model.errors import ConfigurationError
from algotrade.storage.configs.files import MemoryConfigStore
from tests.conftest import REPO_ROOT

SITE = REPO_ROOT / "config" / "site"


def site(name: str) -> dict[str, Any]:
    return tomllib.loads((SITE / f"{name}.toml").read_text())


def test_the_committed_site_files_load() -> None:
    store = MemoryConfigStore(
        {("site", "settings", n): site(n) for n in ("sources", "nightly", "universe")}
    )
    sources, nightly, universe = load_sources(store), load_nightly(store), load_universe(store)
    assert sources.vendor("massive").min_interval_s == 12.5 and sources.actions_window == (-7, 30)
    assert sources.vendor("cboe").enabled and sources.limits_dir == "var/run/limits"
    assert nightly.max_catch_up == 5 and universe.source == "nasdaq_trader"
    defaults = site("defaults")
    assert BacktestSettings.parse(defaults["backtest"], "b") == BacktestSettings()
    assert ScreeningSettings.parse(defaults["screening"], "s") == ScreeningSettings()


def test_missing_files_fall_back_to_defaults() -> None:
    empty = MemoryConfigStore({})
    assert load_sources(empty) == SourcesSettings()
    assert load_nightly(empty) == NightlySettings()
    assert load_universe(empty) == UniverseSettings()


@pytest.mark.parametrize(
    ("doc", "message"),
    [
        ({"retention": 3}, r"sources.toml: unknown keys \['retention'\]"),
        ({"massive": {"min_interval": 1}}, r"sources.toml \[massive\]: unknown keys"),
        ({"cboe": {"days": 3}}, r"\[cboe\]: unknown keys \['days'\]"),
        ({"massive": {"min_interval_s": "fast"}}, r"\[massive\] min_interval_s: expected a number"),
        ({"massive": {"min_interval_s": -1}}, r"expected a number >= 0, got -1"),
        ({"massive": {"corporate_actions_window": [1]}}, "a list of 2 integers"),
        ({"cboe": {"enabled": "yes"}}, r"\[cboe\] enabled: expected true or false"),
        ({"cboe": {"workers": 0}}, r"workers: expected an integer >= 1"),
        ({"cboe": {"workers": True}}, r"workers: expected an integer"),
        ({"http": {"limits_dir": ""}}, "limits_dir: expected a non-empty string"),
        ({"http": 3}, "unknown keys"),
        ({"quality": {"min_chain_coverage": 1.5}}, "a fraction between 0 and 1"),
    ],
)
def test_sources_errors_name_the_key(doc: dict[str, Any], message: str) -> None:
    with pytest.raises(ConfigurationError, match=message):
        SourcesSettings.from_document(doc)


def test_nightly_and_universe_errors_name_the_key() -> None:
    with pytest.raises(ConfigurationError, match=r"nightly.toml \[sessions\] max_catch_up"):
        NightlySettings.from_document({"sessions": {"max_catch_up": 0}})
    with pytest.raises(ConfigurationError, match=r"\[notify\]: unknown keys"):
        NightlySettings.from_document({"notify": {"email": "x"}})
    with pytest.raises(ConfigurationError, match="source: expected one of"):
        UniverseSettings.from_documents({"source": "ftp"})
    with pytest.raises(ConfigurationError, match="security_types: expected a list of strings"):
        UniverseSettings.from_documents({"security_types": "ETF"})
    with pytest.raises(ConfigurationError, match=r"leverage_markers\[1\]"):
        UniverseSettings.from_documents({"leverage_markers": ["ok", "(unclosed"]})


def test_run_defaults_are_typed_with_nested_paths() -> None:
    bt = BacktestSettings.parse({"costs": {"slippage_bps": 2}, "price_adjustment": "none"}, "x")
    assert bt.costs.slippage_bps == 2.0 and bt.price_adjustment == "none"
    with pytest.raises(ConfigurationError, match=r"cfg \[backtest.costs\]: unknown keys"):
        BacktestSettings.parse({"costs": {"fee": 1}}, "cfg [backtest]")
    with pytest.raises(ConfigurationError, match=r"\[backtest.limits\] allow_short"):
        BacktestSettings.parse({"limits": {"allow_short": 1}}, "cfg [backtest]")
    with pytest.raises(ConfigurationError, match="price_adjustment: expected one of"):
        BacktestSettings.parse({"price_adjustment": "dividends"}, "cfg [backtest]")
    with pytest.raises(ConfigurationError, match="max_universe_age_days"):
        ScreeningSettings.parse({"max_universe_age_days": 1.5}, "cfg [screening]")
