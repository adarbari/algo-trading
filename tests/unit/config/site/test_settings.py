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
from algotrade.storage.factory import open_config_store
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
        ({"quality": {"max_chain_fetch_failures": 1.5}}, "a fraction between 0 and 1"),
        ({"quality": {"max_chain_stale_share": -0.1}}, "max_chain_stale_share: expected a number"),
        ({"quality": {"min_chain_coverage": 0.95}}, r"\[quality\]: unknown keys"),
    ],
)
def test_sources_errors_name_the_key(doc: dict[str, Any], message: str) -> None:
    with pytest.raises(ConfigurationError, match=message):
        SourcesSettings.from_document(doc)


def test_nightly_and_universe_errors_name_the_key() -> None:
    with pytest.raises(ConfigurationError, match=r"nightly.toml \[sessions\] max_catch_up"):
        NightlySettings.from_document({"sessions": {"max_catch_up": 0}})
    with pytest.raises(ConfigurationError, match=r"\[notify\]: unknown keys"):
        NightlySettings.from_document({"notify": {"slack": "x"}})
    with pytest.raises(ConfigurationError, match=r"\[notify\] email: expected a table"):
        NightlySettings.from_document({"notify": {"email": "x"}})
    with pytest.raises(
        ConfigurationError, match=r"\[notify.email\] smtp_port: expected an integer"
    ):
        NightlySettings.from_document({"notify": {"email": {"smtp_port": 0}}})
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
    from algotrade.features.registry import GROUPS  # noqa: PLC0415

    doc = tomllib.loads((SITE / "rollups.toml").read_text())
    params = rollup_params(doc, {k: r.params for k, r in GROUPS.items()})
    assert params["option_liquidity@v1"] == GROUPS["option_liquidity@v1"].params  # defaults
    assert params["price_stats@v1"] == GROUPS["price_stats@v1"].params


def figi_store(rows: list[dict[str, str]]) -> MemoryConfigStore:
    return MemoryConfigStore({}, overrides={"figi": rows})


def test_figi_overrides_load_through_the_universe_loader() -> None:
    rows = [
        {"symbol": "dfac", "figi": "BBG011DXY5J0", "note": "first FIGI; vendor flips"},
        {"symbol": "MMEDV", "figi": "", "note": "when-issued line: no FIGI of its own"},
    ]
    settings = load_universe(figi_store(rows))
    assert settings.figi_overrides == {"DFAC": "BBG011DXY5J0", "MMEDV": None}


def test_the_committed_figi_overrides_file_loads() -> None:
    load_universe(open_config_store(REPO_ROOT / "config"))  # header + comments only: valid


@pytest.mark.parametrize(
    ("rows", "message"),
    [
        ([{"symbol": "A", "figi": "BBG1", "note": ""}], "line 2: figi 'BBG1' is not a composite"),
        ([{"symbol": "", "figi": "BBG011DXY5J0", "note": ""}], "line 2: symbol is required"),
        (
            [{"symbol": "A", "figi": "", "note": ""}, {"symbol": "a", "figi": "", "note": ""}],
            "line 3: A is listed twice",
        ),
        (
            [
                {"symbol": "A", "figi": "BBG011DXY5J0", "note": ""},
                {"symbol": "B", "figi": "BBG011DXY5J0", "note": ""},
            ],
            "line 3: BBG011DXY5J0 is forced for two symbols",
        ),
        ([{"symbol": "A", "figi": "", "why": ""}], r"unknown column\(s\) \['why'\]"),
    ],
)
def test_figi_override_errors_name_the_line(rows: list[dict[str, str]], message: str) -> None:
    with pytest.raises(ConfigurationError, match=message):
        load_universe(figi_store(rows))


def test_ibkr_and_verification_settings() -> None:
    from algotrade.config.site.settings import (  # noqa: PLC0415
        VerificationSettings,
        load_verification,
    )

    sources = SourcesSettings.from_document(site("sources"))
    assert not sources.vendor("ibkr").enabled and sources.vendor("ibkr").raw_retention_days == 30
    assert (sources.ibkr.market_data_type, sources.ibkr.stream_wait_s) == (3, 4.0)
    assert (sources.ibkr.connect_timeout_s, sources.ibkr.request_timeout_s) == (10.0, 60.0)
    assert sources.max_verify_failures == 0.10
    store = MemoryConfigStore({("site", "settings", "verification"): site("verification")})
    verification = load_verification(store)
    assert verification == VerificationSettings()  # the file states the defaults
    assert verification.core_symbols[:3] == ("AAPL", "SPY", "QQQ") and verification.rotating == 10
    assert load_verification(MemoryConfigStore({})) == VerificationSettings()
    custom = VerificationSettings.from_document(
        {"sample": {"core_symbols": ["aapl"], "rotating": 0}, "tolerances": {"iv_abs": 0.05}}
    )
    assert (custom.core_symbols, custom.rotating, custom.iv_abs) == (("AAPL",), 0, 0.05)


@pytest.mark.parametrize(
    ("doc", "message"),
    [
        ({"ibkr": {"market_data_type": 5}}, r"\[ibkr\] market_data_type: expected 1 \(live\)"),
        ({"ibkr": {"host": "x"}}, r"\[ibkr\]: unknown keys \['host'\]"),  # host comes from .env
        ({"quality": {"max_verify_failures": 2}}, "a fraction between 0 and 1"),
    ],
)
def test_ibkr_errors_name_the_key(doc: dict[str, Any], message: str) -> None:
    with pytest.raises(ConfigurationError, match=message):
        SourcesSettings.from_document(doc)


def test_verification_errors_name_the_key() -> None:
    from algotrade.config.site.settings import VerificationSettings  # noqa: PLC0415

    with pytest.raises(ConfigurationError, match=r"verification.toml \[sample\]: unknown keys"):
        VerificationSettings.from_document({"sample": {"core": ["A"]}})
    with pytest.raises(ConfigurationError, match="warn_multiple: expected a number >= 1"):
        VerificationSettings.from_document({"tolerances": {"warn_multiple": 0.5}})
