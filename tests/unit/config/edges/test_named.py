"""The named instruments of a time-series edge (ADR 0073): one ``instrument.symbol`` rule over a
short list, and the document rules around ``base = "out_of_window"`` and a named option sleeve's
``base = "delta_equivalent"`` (ADR 0088 decision 14)."""

from dataclasses import asdict
from typing import Any

import pytest

from algotrade.config.edges.document import parse_edge
from algotrade.config.edges.identity import identity_dict
from algotrade.config.edges.named import MAX_NAMED, named_symbols
from algotrade.config.edges.portfolio import TRACKED_INDEXES, TRACKED_LICENCE
from algotrade.config.site.settings import load_macro
from algotrade.config.strategy.schema import Group, Selection, parse_selection
from algotrade.core.model.errors import ConfigurationError
from algotrade.storage.configs.files import FileConfigStore
from tests.conftest import REPO_ROOT
from tests.unit.config.edges.test_document import document

TIMED = {
    "schedule": "calendar:turn_of_month",
    "base": "out_of_window",
    "outcome": {
        "kind": "excess_return",
        "horizon_sessions": [4],
        "benchmark": "none",
        "start_offset_sessions": 1,
    },
    "universe": {"where": {"all": [{"field": "instrument.symbol", "op": "in", "value": ["spy"]}]}},
}


def selection(*rules: dict[str, Any]) -> Any:
    return parse_selection({"name": "n", "where": {"all": list(rules)}}, "x")


def rule(value: Any, op: str = "in", field: str = "instrument.symbol") -> dict[str, Any]:
    return {"field": field, "op": op, "value": value}


def test_symbols_come_upper_cased_once_each_in_order() -> None:
    assert named_symbols(selection(rule(["spy", "QQQ", "SPY"]))) == ("SPY", "QQQ")
    assert named_symbols(selection(rule("iwm", "eq"))) == ("IWM",)


@pytest.mark.parametrize(
    "bad",
    [
        selection(rule(["SPY"], field="instrument.sector")),
        selection(rule(["SPY"], op="not_in")),
        selection(rule(["SPY"]), rule(True, "eq", "instrument.is_etf")),
        selection(rule([f"S{i}" for i in range(MAX_NAMED + 1)])),
        Selection("n", Group("all", ())),
    ],
)
def test_anything_but_a_short_symbol_list_is_refused(bad: Any) -> None:
    with pytest.raises(ConfigurationError, match="time-series edge"):
        named_symbols(bad)


def timed(**changes: Any) -> Any:
    return parse_edge(document(**{**TIMED, **changes}), "drift", "x.toml")


def test_a_time_series_document_parses_with_a_raw_return_outcome() -> None:
    edge = timed()
    assert edge.base == "out_of_window" and edge.outcome.benchmark == "none"


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"schedule": "month_end"}, "needs a calendar or on_market schedule"),
        ({"universe": "liquid_optionable"}, "names its instruments inline"),
        (
            {"universe": {"where": {"all": [rule(["SPY"], field="instrument.is_etf")]}}},
            "names its instruments with one rule",
        ),
        ({"outcome": {**TIMED["outcome"], "benchmark": "SPY"}}, "compares raw returns"),
        ({"variants": [{"id": "v2", "base": "universe"}]}, "no variants"),
    ],
)
def test_a_time_series_document_fails_closed(changes: dict[str, Any], message: str) -> None:
    with pytest.raises(ConfigurationError, match=message):
        timed(**changes)


def test_a_raw_return_outcome_needs_the_time_series_base() -> None:
    with pytest.raises(ConfigurationError, match="needs SPY"):
        document_without_base = {**TIMED, "base": "universe"}
        parse_edge(document(**document_without_base), "drift", "x.toml")


SLEEVE = {
    "schedule": "every_session",
    "base": "delta_equivalent",
    "outcome": {
        "kind": "option_pnl", "horizon_sessions": [2], "benchmark": "none", "tenor_days": 30,
        "position": "short_put", "strike_delta": 0.25, "start_offset_sessions": 1,
    },
    "universe": TIMED["universe"],
    "variant_grid": [{"prefix": "g", "strike_delta": [0.2, 0.3]}],
}  # fmt: skip


def sleeve(**changes: Any) -> Any:
    return parse_edge(document(**{**SLEEVE, **changes}), "drift", "x.toml")


def test_a_named_option_sleeve_has_variants_a_grid_and_any_plain_or_calendar_schedule() -> None:
    edge = sleeve(variants=[{"id": "wide", "outcome": {"strike_delta": 0.15}}])
    assert edge.base == "delta_equivalent" and [v.id for v in edge.variants] == ["wide"]
    assert len(edge.variant_grid) == 1
    assert sleeve(schedule="month_end").schedule == "month_end"
    # a calendar window still fixes the hold at its own length (ADR 0073 decision 2)
    calendar = {**SLEEVE["outcome"], "horizon_sessions": [4]}  # type: ignore[dict-item]
    assert sleeve(schedule="calendar:turn_of_month", outcome=calendar).base == "delta_equivalent"


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        (
            {"outcome": {**TIMED["outcome"], "benchmark": "SPY"}, "variant_grid": None},  # type: ignore[dict-item]
            "pairs an option position with its delta-equivalent",
        ),
        (
            {"outcome": {**SLEEVE["outcome"], "horizon_sessions": [2, 5]}},  # type: ignore[dict-item]
            "one horizon_sessions value",
        ),
        ({"variants": [{"id": "v2", "base": "universe"}]}, "variants keep base"),
        (
            {"variants": [{"id": "v2", "universe": TIMED["universe"]}]},
            "variants hold the edge's own names",
        ),
        ({"universe": "liquid_optionable"}, "base 'delta_equivalent' names its instruments"),
        ({"schedule": "on_event:earnings_reaction"}, "enters at the sessions its schedule"),
    ],
)
def test_a_named_option_sleeve_fails_closed(changes: dict[str, Any], message: str) -> None:
    with pytest.raises(ConfigurationError, match=message):
        sleeve(**changes)


def test_only_a_sleeve_has_the_delta_equivalent_base_and_out_of_window_keeps_no_variants() -> None:
    with pytest.raises(ConfigurationError, match="variants keep base"):
        parse_edge(document(variants=[{"id": "v2", "base": "delta_equivalent"}]), "drift", "x.toml")
    with pytest.raises(ConfigurationError, match="no variants"):
        timed(variants=[{"id": "v2", "outcome": {"cost_bps": 5}}])


def test_only_a_sleeve_tracks_a_cboe_strategy_index() -> None:
    tracked = {**SLEEVE["outcome"], "tracks": "PUT"}  # type: ignore[dict-item]
    assert sleeve(outcome=tracked).outcome.tracks == "PUT"
    assert sleeve().outcome.tracks is None
    with pytest.raises(ConfigurationError, match="tracks"):
        sleeve(outcome={**SLEEVE["outcome"], "tracks": "SPX"})  # type: ignore[dict-item]
    out_of_window = {**TIMED["outcome"], "tracks": "PUT"}
    with pytest.raises(ConfigurationError, match="only a named option sleeve"):
        timed(outcome=out_of_window)


def test_every_tracked_index_is_a_site_cboe_series() -> None:
    site = {s.key: s for s in load_macro(FileConfigStore(REPO_ROOT / "config", local=False)).series}
    assert set(TRACKED_INDEXES) <= set(site)
    assert {site[k].licence for k in TRACKED_INDEXES} == {TRACKED_LICENCE}  # what a figure carries


def test_naming_a_tracked_index_never_changes_the_trials_identity() -> None:
    tracked = sleeve(outcome={**SLEEVE["outcome"], "tracks": "PUT"})  # type: ignore[dict-item]
    assert identity_dict(asdict(tracked)) == identity_dict(asdict(sleeve()))
