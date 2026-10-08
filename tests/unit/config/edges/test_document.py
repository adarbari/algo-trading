"""``parse_edge`` (ADR 0053 decision 1): a full document types into an ``Edge``; every rule
fails closed with the file and the key; rejected and blocked documents need their reason and
may leave the quality bar unanswered."""

from datetime import date
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
        "outcome": {
            "kind": "excess_return",
            "horizon_sessions": [20, 60],
            "benchmark": "SPY",
            "start_offset_sessions": 1,
        },
        "schedule": "on_event:earnings_reaction",
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
            "start_offset_sessions": 1,
            "cost_bps": 20,
        },
        sources=[{"title": "A paper", "url": "https://example.org/a"}],
    )
    assert edge.event_class == "earnings_reaction"
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
        "measure": "realised_to_implied_vol",
        "direction": "below",
        "max_drawdown": 0.5,
        "start_offset_sessions": 1,
    }
    edge = parse(outcome=outcome, schedule="every_session")
    assert (edge.outcome.target, edge.outcome.max_drawdown) == (1.0, 0.5)
    assert (edge.outcome.measure, edge.outcome.direction) == ("realised_to_implied_vol", "below")


def test_a_window_may_start_before_an_event_announced_ahead() -> None:
    outcome = {
        "kind": "excess_return",
        "horizon_sessions": [6],
        "benchmark": "SPY",
        "start_offset_sessions": -5,
    }
    edge = parse(outcome=outcome, schedule="on_event:earnings_expected")
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
    base = {
        "kind": "excess_return", "horizon_sessions": [20], "benchmark": "SPY",
        "start_offset_sessions": 1,
    }  # fmt: skip
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
        (
            {"outcome": _outcome(kind="hit_target", target=1, direction="below")},
            "measure: required for a hit_target",
        ),
        ({"outcome": _outcome(target=1)}, "target: only a hit_target outcome has one"),
        ({"outcome": _outcome(measure="sharpe")}, "measure: expected one of"),
        ({"outcome": _outcome(max_drawdown=1.5)}, "max_drawdown: expected a fraction"),
        ({"outcome": _outcome(cost_bps=-1)}, "cost_bps: expected a number >= 0"),
        (
            {"outcome": _outcome(start_offset_sessions=-5)},
            "an entry before the event needs it announced ahead",
        ),
        (
            {"outcome": _outcome(start_offset_sessions=0)},
            "an entry before the event needs it announced ahead",
        ),
        (
            {"outcome": _outcome(start_offset_sessions=0), "schedule": "every_session"},
            "the entry session is at least 1 session later",
        ),
        (
            {"outcome": _outcome(start_offset_sessions=None), "schedule": "month_end"},
            "the entry session is at least 1 session later",
        ),
        ({"base": "event", "schedule": "month_end"}, "base: 'event' needs an on_event schedule"),
        ({"base": "all"}, "base: expected one of"),
        ({"api_key": "x"}, "looks like a secret"),
    ],
)
def test_every_rule_fails_closed_with_the_file_and_key(
    changes: dict[str, Any], message: str
) -> None:
    with pytest.raises(ConfigurationError, match=message) as caught:
        parse(**changes)
    assert "drift" in str(caught.value)


def test_the_frozen_period_start_is_optional_and_a_date() -> None:
    assert parse().frozen_from is None
    assert parse(frozen_from=date(2026, 4, 1)).frozen_from == date(2026, 4, 1)
    assert parse(frozen_from="2026-04-01").frozen_from == date(2026, 4, 1)
    for bad in ("last quarter", 20260401, "2026-13-01"):
        with pytest.raises(ConfigurationError, match="frozen_from"):
            parse(frozen_from=bad)


def test_event_and_universe_bases_default_by_schedule() -> None:
    assert parse().base == "event"
    assert parse(base="universe").base == "universe"
    assert parse(schedule="month_end").base == "universe"


def test_an_event_announced_ahead_may_enter_before_on_or_after_the_anchor() -> None:
    for offset in (-5, 0, 1):
        outcome = _outcome(start_offset_sessions=offset, horizon_sessions=[6])
        edge = parse(outcome=outcome, schedule="on_event:earnings_expected")
        assert edge.outcome.start_offset_sessions == offset


def test_variants_override_the_outcome_and_the_universe_each_with_its_own_id() -> None:
    rule = {"field": "instrument.status", "op": "eq", "value": "ACTIVE"}
    edge = parse(
        variants=[
            {"id": "micro", "universe": {"where": {"all": [rule]}}},
            {"id": "long_hold", "outcome": {"horizon_sessions": [60], "cost_bps": 40}},
        ]
    )
    micro, hold = edge.variants
    assert isinstance(micro.universe, Selection) and micro.outcome == edge.outcome
    assert hold.universe == edge.universe
    assert hold.outcome.horizon_sessions == (60,) and hold.outcome.cost_bps == 40.0
    assert hold.outcome.kind == edge.outcome.kind  # the rest is the edge's own
    assert parse().variants == ()


@pytest.mark.parametrize(
    ("variants", "message"),
    [
        ([{"id": "main"}], "'main' is reserved or listed twice"),
        ([{"id": "a"}, {"id": "a"}], "'a' is reserved or listed twice"),
        ([{"id": "A b"}], "invalid variant id"),
        ([{"outcome": {"cost_bps": 1}}], "id: required"),
        ([{"id": "a", "colour": "red"}], "unknown keys"),
        ([{"id": "a", "outcome": {"horizon_sessions": [60, 20]}}], "horizon_sessions: expected"),
        ([{"id": "a", "outcome": {"start_offset_sessions": 0}}], "an entry before the event"),
        ("a", "expected \\[\\[variants\\]\\] tables"),
    ],
)
def test_a_variant_is_checked_like_the_edge(variants: Any, message: str) -> None:
    with pytest.raises(ConfigurationError, match=message):
        parse(variants=variants)


def test_the_evidence_table_is_optional_and_needs_both_keys() -> None:
    assert parse().evidence is None
    found = parse(evidence={"run_id": "r1", "split_from": "2026-04-01"}).evidence
    assert found is not None and (found.run_id, found.split_from) == ("r1", date(2026, 4, 1))
    for bad in ({"run_id": "r1"}, {"split_from": "2026-04-01"}, {"run_id": "r", "split_from": "x"}):
        with pytest.raises(ConfigurationError, match="evidence"):
            parse(evidence=bad)
    with pytest.raises(ConfigurationError, match="unknown keys"):
        parse(evidence={"run_id": "r1", "split_from": "2026-04-01", "extra": 1})


# ---- expires_otm and kind-changing variants (ED4a) --------------------------------------

OTM = {
    "kind": "expires_otm", "horizon_sessions": [15, 21], "benchmark": "none", "structure": "put",
    "strike_delta": 0.3, "iv_field": "rollup.ibkr_iv@v1.iv30_ibkr", "start_offset_sessions": 1,
}  # fmt: skip


def otm(**changes: Any) -> dict[str, Any]:
    return document(schedule="every_session", outcome={**OTM, **changes})


def test_an_expires_otm_outcome_types_its_structure_strike_and_iv_field() -> None:
    o = parse_edge(otm(), "drift", WHERE).outcome
    assert (o.structure, o.strike_delta, o.otm_pct) == ("put", 0.3, None)
    assert o.iv_field == "rollup.ibkr_iv@v1.iv30_ibkr" and o.target is None


@pytest.mark.parametrize(
    "changes,match",
    [
        ({"strike_delta": None}, "exactly one of strike_delta and otm_pct"),
        ({"otm_pct": 0.05}, "exactly one of strike_delta and otm_pct"),
        ({"strike_delta": 1.2}, "strike_delta: expected a fraction in"),
        ({"structure": "straddle"}, "structure"),
        ({"structure": None}, "structure: required"),
        ({"iv_field": None}, "iv_field: required"),
        ({"target": 1.0}, "target: only a hit_target outcome has one"),
    ],
)
def test_an_expires_otm_outcome_fails_closed(changes: dict[str, Any], match: str) -> None:
    body = {k: v for k, v in {**OTM, **changes}.items() if v is not None}
    with pytest.raises(ConfigurationError, match=match):
        parse_edge(document(schedule="every_session", outcome=body), "drift", WHERE)


def test_only_an_expires_otm_outcome_has_a_structure_or_strike() -> None:
    plain = {"kind": "excess_return", "horizon_sessions": [5], "benchmark": "SPY",
             "start_offset_sessions": 1}  # fmt: skip
    with pytest.raises(ConfigurationError, match="only an expires_otm outcome has one"):
        parse_edge(
            document(schedule="every_session", outcome={**plain, "otm_pct": 0.1}), "drift", WHERE
        )


def test_a_variant_overrides_the_strike_and_a_variant_of_another_kind_drops_the_old_keys() -> None:
    doc = otm()
    doc["variants"] = [
        {"id": "d16", "outcome": {"strike_delta": 0.16}},
        {"id": "ratio", "outcome": {"kind": "hit_target", "measure": "realised_to_implied_vol",
                                    "direction": "below", "target": 1.0}},
    ]  # fmt: skip
    d16, ratio = parse_edge(doc, "drift", WHERE).variants
    assert d16.outcome.strike_delta == 0.16 and d16.outcome.structure == "put"
    assert ratio.outcome.kind == "hit_target" and ratio.outcome.structure is None
    assert ratio.outcome.iv_field == "rollup.ibkr_iv@v1.iv30_ibkr"  # shared keys survive
    assert ratio.outcome.horizon_sessions == (15, 21)
