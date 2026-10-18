"""The named instruments of a time-series edge (ADR 0073): one ``instrument.symbol`` rule over a
short list, and the document rules around ``base = "out_of_window"``."""

from typing import Any

import pytest

from algotrade.config.edges.document import parse_edge
from algotrade.config.edges.named import MAX_NAMED, named_symbols
from algotrade.config.strategy.schema import Group, Selection, parse_selection
from algotrade.core.model.errors import ConfigurationError
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
        ({"schedule": "month_end"}, "needs a calendar schedule"),
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
