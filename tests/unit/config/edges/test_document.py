"""``parse_edge`` (ADR 0053 decision 1): a full document types into an ``Edge``; every rule
fails closed with the file and the key; rejected and blocked documents need their reason and
may leave the quality bar unanswered."""

from typing import Any

import pytest

from algotrade.config.edges.document import QUALITY_BAR, Edge, parse_edge
from algotrade.config.strategy.schema import Selection
from algotrade.core.model.errors import ConfigurationError

WHERE = "config/site/edges/drift.toml"


def document(**changes: Any) -> dict[str, Any]:
    doc: dict[str, Any] = {
        "id": "drift",
        "name": "Drift",
        "thesis": "Small names drift after earnings.",
        "mechanism": "Underreaction.",
        "persistence": "Limits to arbitrage.",
        "outcome": {"kind": "excess_return", "horizon_sessions": [20, 60], "benchmark": "SPY"},
        "schedule": "on_event:earnings",
        "universe": "liquid_optionable",
        "top_k": "all",
        "screeners": [],
        "status": "candidate",
        "sources": [{"title": "Bernard and Thomas, 1989"}],
        "quality_bar": {key: f"answer {key}" for key in QUALITY_BAR},
    }
    doc.update(changes)
    return {k: v for k, v in doc.items() if v is not None}


def parse(**changes: Any) -> Edge:
    return parse_edge(document(**changes), "drift", WHERE)


def test_a_full_document_types_into_an_edge() -> None:
    edge = parse(
        notes="  the cap\n  is open ",
        outcome={
            "kind": "excess_return",
            "horizon_sessions": [20, 60],
            "benchmark": "SPY",
            "cost_bps": 20,
        },
        sources=[{"title": "A paper", "url": "https://example.org/a"}],
    )
    assert edge.event_class == "earnings"
    assert edge.outcome.horizon_sessions == (20, 60)
    assert edge.outcome.cost_bps == 20.0
    assert edge.top_k is None
    assert edge.universe == "liquid_optionable"
    assert edge.notes == "the cap is open"
    assert edge.sources[0].url == "https://example.org/a"
    assert [k for k, _ in edge.answers][:3] == ["mechanism", "persistence", "outcome"]
    assert len(edge.answers) == 9


def test_an_inline_universe_is_a_selection_named_after_the_edge() -> None:
    rule = {"field": "instrument.status", "op": "eq", "value": "ACTIVE"}
    edge = parse(universe={"where": {"all": [rule]}}, top_k=5, schedule="month_end")
    assert isinstance(edge.universe, Selection)
    assert edge.universe.name == "drift"
    assert edge.top_k == 5
    assert edge.event_class is None


def test_a_hit_target_with_a_drawdown_cap_and_no_benchmark() -> None:
    outcome = {
        "kind": "hit_target",
        "horizon_sessions": [20],
        "benchmark": "none",
        "target": 1.0,
        "max_drawdown": 0.5,
    }
    edge = parse(outcome=outcome, schedule="every_session")
    assert (edge.outcome.target, edge.outcome.max_drawdown) == (1.0, 0.5)


def test_a_window_may_start_before_an_event_announced_ahead() -> None:
    outcome = {
        "kind": "excess_return",
        "horizon_sessions": [6],
        "benchmark": "SPY",
        "start_offset_sessions": -5,
    }
    edge = parse(outcome=outcome, schedule="on_event:earnings_scheduled")
    assert edge.outcome.start_offset_sessions == -5


@pytest.mark.parametrize("status", ["rejected", "blocked"])
def test_a_closed_edge_needs_its_reason_and_may_skip_the_bar(status: str) -> None:
    edge = parse(status=status, rejection_reason="Gone.", quality_bar={}, mechanism=None)
    assert edge.rejection_reason == "Gone."
    assert edge.quality_bar["decoys"] == ""
    with pytest.raises(ConfigurationError, match="rejection_reason: required"):
        parse(status=status)


def test_a_retired_edge_may_carry_a_reason() -> None:
    assert parse(status="retired", rejection_reason="Decayed.").rejection_reason == "Decayed."


def _outcome(**changes: Any) -> dict[str, Any]:
    base = {"kind": "excess_return", "horizon_sessions": [20], "benchmark": "SPY"}
    return {k: v for k, v in {**base, **changes}.items() if v is not None}


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"colour": "red"}, "unknown keys \\['colour'\\]"),
        ({"id": "other"}, "id: 'other' must equal the file name 'drift'"),
        ({"id": None}, "id: required"),
        ({"status": None}, "status: required"),
        ({"status": "maybe"}, "status: expected one of"),
        ({"thesis": "One. Two."}, "thesis: expected one sentence"),
        ({"thesis": "No full stop"}, "thesis: expected one sentence"),
        ({"mechanism": None}, "mechanism: required"),
        ({"schedule": "weekly"}, "schedule: expected one of"),
        ({"schedule": "on_event:eclipse"}, "schedule: expected one of"),
        ({"universe": 3}, "universe: expected a selection preset name"),
        ({"universe": {"where": {"all": []}}}, "universe.where.all: expected a non-empty list"),
        ({"top_k": 0}, "top_k: expected an integer >= 1 or 'all'"),
        ({"top_k": "most"}, "top_k: expected an integer >= 1 or 'all'"),
        ({"screeners": ["a", "a"]}, "screeners: a screener is listed twice"),
        ({"baselines": "size"}, "baselines: expected a list of strings"),
        ({"sources": []}, "sources: expected one or more"),
        ({"sources": [{"title": "x", "url": "http://a"}]}, "url: expected an https://"),
        ({"sources": [{"url": "https://a"}]}, "title: required"),
        ({"quality_bar": None}, "quality_bar: required"),
        ({"quality_bar": {"outcome": "x"}}, "trigger_timing: required"),
        ({"quality_bar": {"why": "x"}}, "unknown keys \\['why'\\]"),
        ({"rejection_reason": "No."}, "only a rejected, blocked or retired edge"),
        ({"outcome": None}, "outcome: required"),
        ({"outcome": _outcome(kind=None)}, "kind: required"),
        ({"outcome": _outcome(kind="sharpe")}, "kind: expected one of"),
        ({"outcome": _outcome(benchmark=None)}, "benchmark: required"),
        ({"outcome": _outcome(benchmark="none")}, "an excess return needs SPY"),
        ({"outcome": _outcome(horizon_sessions=[])}, "horizon_sessions: expected one or more"),
        ({"outcome": _outcome(horizon_sessions=[60, 20])}, "ascending, distinct"),
        ({"outcome": _outcome(horizon_sessions=[0])}, "integers >= 1"),
        ({"outcome": _outcome(kind="hit_target")}, "target: required for a hit_target"),
        ({"outcome": _outcome(max_drawdown=1.5)}, "max_drawdown: expected a fraction"),
        ({"outcome": _outcome(cost_bps=-1)}, "cost_bps: expected a number >= 0"),
        (
            {"outcome": _outcome(start_offset_sessions=-5)},
            "a window may start before the event only when it is announced ahead",
        ),
        (
            {"outcome": _outcome(start_offset_sessions=1), "schedule": "every_session"},
            "only an on_event schedule has an offset",
        ),
        ({"api_key": "x"}, "looks like a secret"),
    ],
)
def test_every_rule_fails_closed_with_the_file_and_key(
    changes: dict[str, Any], message: str
) -> None:
    with pytest.raises(ConfigurationError, match=message) as caught:
        parse(**changes)
    assert "drift" in str(caught.value)
