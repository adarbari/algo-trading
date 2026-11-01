"""The ``on_market:<trigger>`` schedule (ADR 0075): its parsing, and the document loader that
accepts it only as a time-series edge (a named universe of 1 to 10 instruments, base
``out_of_window``, benchmark ``none``, one horizon, no variants) and refuses everything else."""

from typing import Any

import pytest

from algotrade.config.edges import document
from algotrade.config.edges.document import QUALITY_BAR, parse_edge
from algotrade.config.edges.schedules import markets
from algotrade.config.site.fields import Table
from algotrade.core.model.errors import ConfigurationError
from algotrade.features.rollups.market.edges import triggers

NAMED = {"where": {"all": [{"field": "instrument.symbol", "op": "in", "value": ["SPY", "QQQ"]}]}}


def doc(**changes: Any) -> dict[str, Any]:
    out: dict[str, Any] = {
        "id": "vix", "name": "After a VIX spike", "thesis": "Fear is overpriced.",
        "mechanism": "m", "persistence": "p",
        "outcome": {
            "kind": "excess_return", "horizon_sessions": [10], "benchmark": "none",
            "start_offset_sessions": 1,
        },
        "schedule": "on_market:vix_spike", "base": "out_of_window", "universe": NAMED,
        "top_k": "all", "screeners": [], "status": "candidate", "sources": [{"title": "A paper"}],
        "quality_bar": {k: f"answer {k}" for k in QUALITY_BAR},
    }  # fmt: skip
    out.update(changes)
    return {k: v for k, v in out.items() if v is not None}


def edge(**changes: Any) -> document.Edge:
    return parse_edge(doc(**changes), "vix", "vix.toml")


def outcome(**changes: Any) -> dict[str, Any]:
    return {**doc()["outcome"], **changes}


def test_document_reexports_the_same_objects() -> None:
    for name in ("MARKET_TRIGGERS", "ON_MARKET", "market_trigger"):
        assert getattr(document, name) is getattr(markets, name)


def test_schedule_parts_and_fail_closed_triggers() -> None:
    t = Table({}, "edge.toml")
    assert markets.market_trigger("on_market:vix_spike") == "vix_spike"
    assert markets.market_trigger("month_end") is None
    assert markets.market_schedule_ok(t, "on_market:vix_spike")
    assert not markets.market_schedule_ok(t, "month_end")
    with pytest.raises(ConfigurationError, match="not a market trigger"):
        markets.market_schedule_ok(t, "on_market:fomc_dot_plot")


def test_a_market_edge_loads_with_its_trigger() -> None:
    e = edge()
    assert e.market_trigger == "vix_spike" and e.event_class is None
    assert (e.base, e.outcome.horizon_sessions, e.outcome.benchmark) == (
        "out_of_window",
        (10,),
        "none",
    )


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"schedule": "on_market:nope"}, "not a market trigger"),
        ({"base": "universe"}, "base = 'out_of_window'"),  # a cross-section base is refused
        ({"base": None}, "base = 'out_of_window'"),  # the default base is the universe
        ({"base": "event"}, "base = .out_of_window."),
        ({"universe": "sp500"}, "inline"),  # a preset, not a named universe
        ({"universe": {"where": {"all": [{"field": "instrument.symbol", "op": "in",
                                          "value": [f"S{i}" for i in range(11)]}]}}},
         "1 to 10 named"),
        ({"outcome": outcome(benchmark="SPY")}, "raw returns"),
        ({"outcome": outcome(horizon_sessions=[5, 10])}, "one horizon_sessions"),
        ({"outcome": outcome(start_offset_sessions=2)}, "start_offset_sessions = 1"),
        ({"variants": [{"id": "v", "universe": NAMED}]}, "no variants"),
    ],
)  # fmt: skip
def test_a_market_edge_is_refused_unless_it_is_a_time_series_edge(
    changes: dict[str, Any], message: str
) -> None:
    with pytest.raises(ConfigurationError, match=message):
        edge(**changes)


def test_every_trigger_field_is_a_declared_column_of_the_market_triggers_group() -> None:
    """The fields the placement reads exist (kept equal to the group's declaration)."""
    prefix = f"market.{triggers.NAME}@v{triggers.VERSION}."
    for field in (*markets.MARKET_TRIGGERS.values(), *markets.MARKET_TRIGGER_AGE.values()):
        assert field.startswith(prefix) and field.removeprefix(prefix) in triggers.COLUMNS
    assert markets.MARKET_TRIGGERS.keys() == markets.MARKET_TRIGGER_AGE.keys()
