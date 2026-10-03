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
    assert sources.vendor("sec_edgar").raw_retention_days == 7
    assert sources.vendor("cboe").raw_retention_days is None  # the global window
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
        ({"sec_edgar": {"raw_retention_days": 0}}, r"\[sec_edgar\] raw_retention_days: expected"),
        ({"sec_edgar": {"raw_retention_days": 1.5}}, r"raw_retention_days: expected an integer"),
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


def test_rebalance_selection_is_typed() -> None:
    default = BacktestSettings()
    assert (default.rebalance_selection, default.selection_lag_sessions) == ("none", 1)
    for value in ("none", "monthly", "weekly", "21d", "1d"):
        assert (
            BacktestSettings.parse({"rebalance_selection": value}, "x").rebalance_selection == value
        )
    bt = BacktestSettings.parse({"selection_lag_sessions": 3}, "x")
    assert bt.selection_lag_sessions == 3
    for bad in ("daily", "0d", "d", "monthly ", "-2d"):
        with pytest.raises(ConfigurationError, match=r"cfg \[backtest\] rebalance_selection"):
            BacktestSettings.parse({"rebalance_selection": bad}, "cfg [backtest]")
    with pytest.raises(ConfigurationError, match="rebalance_selection: expected a non-empty"):
        BacktestSettings.parse({"rebalance_selection": 30}, "cfg [backtest]")
    for lag in (0, 1.5, True):
        with pytest.raises(ConfigurationError, match="selection_lag_sessions"):
            BacktestSettings.parse({"selection_lag_sessions": lag}, "cfg [backtest]")


@pytest.mark.parametrize(
    ("doc", "message"),
    [
        ({"leverage_patterns": [r"(\d)x"]}, r"leverage_patterns\[0\]: needs a named group"),
        ({"leverage_patterns": [r"(?P<n>"]}, r"leverage_patterns\[0\]"),
        ({"leverage_exclusions": ["ok", "[bad"]}, r"leverage_exclusions\[1\]"),
        ({"inverse_markers": "short"}, "inverse_markers: expected a list of strings"),
        ({"leverage_conventions": {"pattern": "x"}}, "expected a list of tables"),
        ({"leverage_conventions": [{"pattern": "x"}]}, r"leverage_conventions\[0\]: expected"),
        (
            {"leverage_conventions": [{"pattern": "(", "leverage": 2}]},
            r"leverage_conventions\[0\] pattern",
        ),
        (
            {"leverage_conventions": [{"pattern": "x", "leverage": 0}]},
            "leverage: expected a non-zero number",
        ),
        (
            {"leverage_conventions": [{"pattern": "x", "leverage": "2"}]},
            "leverage: expected a number",
        ),
    ],
)
def test_leverage_rule_errors_name_the_key(doc: dict[str, Any], message: str) -> None:
    with pytest.raises(ConfigurationError, match=message):
        UniverseSettings.from_documents(doc)


def test_leverage_rules_load_in_order() -> None:
    doc = {
        "leverage_conventions": [
            {"pattern": "^A Ultra Short", "leverage": -2},
            {"pattern": "^A Ultra", "leverage": 2.5},
        ],
        "leverage_patterns": [r"(?P<n>\d)x"],
    }
    settings = UniverseSettings.from_documents(doc)
    assert settings.leverage_conventions == (("^A Ultra Short", -2.0), ("^A Ultra", 2.5))
    assert settings.leverage_patterns == (r"(?P<n>\d)x",)


# ----------------------------------------------------------------------------- rollups.toml


def test_rollup_params_typed_from_the_declared_defaults() -> None:
    from dataclasses import dataclass  # noqa: PLC0415

    from algotrade.config.site.settings import load_rollups, rollup_params  # noqa: PLC0415

    @dataclass(frozen=True)
    class Params:
        n: int = 5
        x: float = 0.5
        on: bool = True
        label: str = "a"
        fixed: tuple[int, ...] = (1, 2)  # not scalar: not a key

        def __post_init__(self) -> None:
            if self.n > 100:
                raise ValueError("n too big")

    declared = {"r@v1": Params(), "plain@v1": None}
    doc = {"r@v1": {"n": 7, "x": 1, "on": False, "label": "b"}}
    out = rollup_params(doc, declared)
    assert out == {"r@v1": Params(7, 1.0, False, "b"), "plain@v1": None}
    assert rollup_params(None, declared)["r@v1"] == Params()
    for bad, problem in (
        ({"other@v1": {}}, "unknown keys"),
        ({"plain@v1": {}}, "unknown keys"),
        ({"r@v1": {"fixed": [1]}}, "unknown keys"),
        ({"r@v1": {"n": "7"}}, "expected an integer"),
        ({"r@v1": {"n": 101}}, r"rollups.toml \[r@v1\]: n too big"),
    ):
        with pytest.raises(ConfigurationError, match=problem):
            rollup_params(bad, declared)
    store = MemoryConfigStore({("site", "settings", "rollups"): doc})
    assert load_rollups(store, declared)["r@v1"].n == 7


def test_site_rollups_toml_loads_for_every_registered_rollup() -> None:
    from algotrade.config.site.settings import rollup_params  # noqa: PLC0415
    from algotrade.features.registry import ROLLUPS  # noqa: PLC0415

    doc = tomllib.loads((SITE / "rollups.toml").read_text())
    params = rollup_params(doc, {k: r.params for k, r in ROLLUPS.items()})
    assert params["option_liquidity@v1"] == ROLLUPS["option_liquidity@v1"].params  # defaults
    assert params["price_stats@v1"] == ROLLUPS["price_stats@v1"].params
