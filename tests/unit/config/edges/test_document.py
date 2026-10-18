"""``parse_edge`` (ADR 0053 decision 1): a full document types into an ``Edge``; every rule
fails closed with the file and the key; rejected and blocked documents need their reason and
may leave the quality bar unanswered."""

import tomllib
from dataclasses import asdict, fields
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from algotrade.config.edges.chain import MODEL_STRUCTURES, tenor_sessions
from algotrade.config.edges.document import (
    QUALITY_BAR,
    STATUSES,
    Edge,
    Published,
    expand_baselines,
    parse_edge,
)
from algotrade.config.edges.follow import AUDIT_LABELS, BOOKMARK_LABELS, Follow
from algotrade.config.edges.identity import SIDES, identity_dict
from algotrade.config.strategy.schema import Selection
from algotrade.core.model.errors import ConfigurationError
from algotrade.storage.tables.edge_schemas import EDGE_EVAL, EDGE_LEGS, EDGE_TRADES
from tests.unit.services.evaluation.cross_section.conftest import edge

WHERE = "config/site/edges/drift/edge.toml"


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
        ({"outcome": _outcome(side="flat")}, "side: expected one of"),
        ({"outcome": _outcome(borrow_bps_annual=50)}, "only a short leg pays borrow"),
        (
            {"outcome": _outcome(side="short", max_drawdown=0.2), "top_k": 5},
            "'short' needs an excess_return outcome with no max_drawdown",
        ),
        (
            {
                "outcome": _outcome(
                    side="long_short",
                    kind="hit_target",
                    target=1,
                    measure="excess_return",
                    direction="above",
                ),
                "top_k": 5,
            },
            "'long_short' needs an excess_return outcome",
        ),
        ({"outcome": _outcome(side="short")}, "a 'short' outcome ranks the names"),  # top_k all
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
    found = parse(
        status="evidenced", evidence={"run_id": "r1", "split_from": "2026-04-01"}
    ).evidence
    assert found is not None and (found.run_id, found.split_from) == ("r1", date(2026, 4, 1))
    for bad in ({"run_id": "r1"}, {"split_from": "2026-04-01"}, {"run_id": "r", "split_from": "x"}):
        with pytest.raises(ConfigurationError, match="evidence"):
            parse(status="evidenced", evidence=bad)
    with pytest.raises(ConfigurationError, match="unknown keys"):
        parse(status="evidenced", evidence={"run_id": "r1", "split_from": "2026-04-01", "extra": 1})


def test_evidence_is_only_for_an_evidenced_live_or_retired_edge() -> None:
    cited = {"run_id": "r1", "split_from": "2026-04-01"}
    for status in ("evidenced", "live", "retired"):
        assert parse(status=status, evidence=cited).evidence is not None
    with pytest.raises(ConfigurationError, match="only an evidenced, live or retired"):
        parse(status="candidate", evidence=cited)


def test_a_variant_may_override_base_and_picks_each_checked_like_the_edges() -> None:
    edge = parse(
        schedule="on_event:earnings_reaction",
        variants=[{"id": "decoy", "base": "universe", "picks": "universe"}, {"id": "plain"}],
    )
    decoy, plain = edge.variants
    assert (decoy.base, decoy.picks) == ("universe", "universe")
    assert (plain.base, plain.picks) == (None, None) and edge.picks == "event"
    with pytest.raises(ConfigurationError, match="picks"):
        parse(schedule="on_event:earnings_reaction", variants=[{"id": "x", "picks": "all"}])
    with pytest.raises(ConfigurationError, match="needs an on_event"):
        parse(schedule="month_end", variants=[{"id": "x", "base": "event"}])


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"picks": "universe", "base": "event"}, "needs base"),
        ({"picks": "universe", "variants": [{"id": "x", "base": "event"}]}, "needs base"),
        (
            {"base": "universe", "variants": [{"id": "x", "picks": "universe", "base": "event"}]},
            "needs base",
        ),
        ({"schedule": "month_end", "picks": "universe", "base": "universe"}, "needs an on_event"),
        (
            {"schedule": "month_end", "variants": [{"id": "x", "picks": "event"}]},
            "needs an on_event",
        ),
    ],
)
def test_picks_from_the_universe_need_the_universe_base_and_an_event_schedule(
    changes: Any, message: str
) -> None:
    with pytest.raises(ConfigurationError, match=message):
        parse(**changes)


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


MODEL = {
    "kind": "option_model_pnl", "horizon_sessions": [10], "benchmark": "none",
    "start_offset_sessions": 1, "structure": "atm_straddle_long",
    "iv_field": "rollup.ibkr_iv@v1.iv30_ibkr",
}  # fmt: skip


def model(**changes: Any) -> dict[str, Any]:
    body = {k: v for k, v in {**MODEL, **changes}.items() if v is not None}
    return document(schedule="every_session", outcome=body)


@pytest.mark.parametrize("structure", MODEL_STRUCTURES)
def test_an_option_model_pnl_outcome_types_each_structure_and_is_labelled_model(
    structure: str,
) -> None:
    o = parse_edge(model(structure=structure, cost_bps=5), "drift", WHERE).outcome
    assert (o.structure, o.strike_delta, o.otm_pct, o.cost_bps) == (structure, None, None, 5)
    assert o.iv_field == "rollup.ibkr_iv@v1.iv30_ibkr"
    assert o.basis == "model" and not o.is_return


def test_only_an_option_model_pnl_outcome_is_labelled_model() -> None:
    assert parse_edge(otm(), "drift", WHERE).outcome.basis is None


@pytest.mark.parametrize(
    "changes,match",
    [
        ({"structure": "put"}, "structure"),  # an expires_otm structure is not a model one
        ({"structure": None}, "structure: required"),
        ({"iv_field": None}, "iv_field: required"),
        ({"strike_delta": 0.3}, "at the money, it has no strike"),
        ({"otm_pct": 0.05}, "at the money, it has no strike"),
        ({"benchmark": "SPY"}, "has no benchmark"),
    ],
)
def test_an_option_model_pnl_outcome_fails_closed(changes: dict[str, Any], match: str) -> None:
    with pytest.raises(ConfigurationError, match=match):
        parse_edge(model(**changes), "drift", WHERE)


@pytest.mark.parametrize("horizons", [[10], [21], [42], [10, 21, 42]])
def test_an_option_model_pnl_horizon_within_half_to_double_the_iv_tenor_parses(
    horizons: list[int],
) -> None:
    assert parse_edge(model(horizon_sessions=horizons), "drift", WHERE).outcome.horizon_sessions


@pytest.mark.parametrize("horizons", [[1], [5], [9], [43], [21, 63]])
def test_an_option_model_pnl_horizon_the_30_day_iv_cannot_price_is_refused(
    horizons: list[int],
) -> None:
    with pytest.raises(ConfigurationError, match=r"outside 10\.\.42 sessions"):
        parse_edge(model(horizon_sessions=horizons), "drift", WHERE)


def test_an_option_model_pnl_iv_field_with_no_tenor_in_its_name_is_refused() -> None:
    with pytest.raises(ConfigurationError, match="names no tenor"):
        parse_edge(model(iv_field="feature.my_iv"), "drift", WHERE)


def test_the_tenor_of_an_iv_field_is_read_from_its_name() -> None:
    assert tenor_sessions("rollup.iv30@v1.iv30") == 21
    assert tenor_sessions("rollup.ibkr_iv@v1.iv30_ibkr") == 21
    assert tenor_sessions("rollup.ibkr_iv@v1.rank") is None


def test_an_expires_otm_structure_is_not_a_model_one_and_the_reverse() -> None:
    with pytest.raises(ConfigurationError, match="structure"):
        parse_edge(otm(structure="atm_straddle_long"), "drift", WHERE)


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


def test_a_promoted_screener_must_be_one_the_edge_lists() -> None:
    assert edge().promoted is None
    ok = edge(screeners=["momo", "mod"], implementation={"promoted": "mod"})
    assert ok.promoted == "mod"
    with pytest.raises(ConfigurationError, match="not one of the screeners"):
        edge(implementation={"promoted": "other"})
    with pytest.raises(ConfigurationError, match="promoted"):
        edge(implementation={})


def test_a_declared_basis_horizon_is_one_of_the_outcomes_horizons() -> None:
    assert edge().basis_horizon is None
    e = edge(implementation={"horizon": 2})  # a horizon alone: no promoted screener needed
    assert (e.basis_horizon, e.promoted) == (2, None)
    both = edge(screeners=["momo", "mod"], implementation={"promoted": "mod", "horizon": 2})
    assert (both.basis_horizon, both.promoted) == (2, "mod")
    with pytest.raises(ConfigurationError, match="not one of the outcome's horizon_sessions"):
        edge(implementation={"horizon": 7})
    with pytest.raises(ConfigurationError, match="promoted"):
        edge(implementation={"horizon": 2, "compared": []})  # compared needs the promotion


def test_the_numbers_a_promotion_rests_on_are_parsed_and_checked() -> None:
    row = {
        "horizon": 2, "screener": "mod", "lift": 1.3, "decile_spread": 0.02,
        "sessions": 45, "decile_sessions": 44,
    }  # fmt: skip
    e = edge(
        screeners=["momo", "mod"],
        implementation={"promoted": "mod", "compared": [row]},
    )
    (c,) = e.compared
    assert (c.horizon, c.screener, c.lift, c.sessions, c.decile_sessions) == (2, "mod", 1.3, 45, 44)
    with pytest.raises(ConfigurationError, match="decile_sessions"):
        bad = {k: v for k, v in row.items() if k != "decile_sessions"}
        edge(screeners=["momo", "mod"], implementation={"promoted": "mod", "compared": [bad]})


def test_edge_lifecycle_has_one_vocabulary() -> None:
    """An edge has one status (ADR 0053 amendment 2026-10-10); following is a bookmark, not a
    second lifecycle: no lifecycle word is spoken by two vocabularies."""
    assert {f.name for f in fields(Follow)} == {"since", "labels"}
    assert STATUSES == (
        "researching", "candidate", "evidenced", "live", "retired", "rejected", "blocked",
    )  # fmt: skip
    assert set(BOOKMARK_LABELS) <= set(AUDIT_LABELS)
    assert not set(STATUSES) & set(AUDIT_LABELS)
    assert not {"following", "trial", "followed"} & set(STATUSES)


def test_the_published_table_is_optional_typed_and_checked_against_the_document() -> None:
    assert parse().published is None
    found = parse(
        outcome={
            "kind": "excess_return",
            "horizon_sessions": [20, 60],
            "benchmark": "SPY",
            "start_offset_sessions": 1,
        },
        sources=[{"title": "A"}, {"title": "B"}],
        published={
            "measure": "decile_spread",
            "value": 0.0131,
            "horizon_sessions": 60,
            "source": 1,
            "sample": 25,
        },
    ).published
    assert found == Published("decile_spread", 0.0131, 60, 1, 25, "long_short")
    no_sample = {"measure": "lift_pts", "value": 4, "horizon_sessions": 20, "source": 0}
    assert parse(published=no_sample).published == Published("lift_pts", 4.0, 20, 0, None, "long")


@pytest.mark.parametrize(
    ("published", "match"),
    [
        ({"measure": "sharpe", "value": 1, "horizon_sessions": 20, "source": 0}, "measure"),
        ({"value": 1, "horizon_sessions": 20, "source": 0}, "measure: required"),
        ({"measure": "lift_pts", "horizon_sessions": 20, "source": 0}, "value: required"),
        ({"measure": "lift_pts", "value": 1, "source": 0}, "horizon_sessions: required"),
        ({"measure": "lift_pts", "value": 1, "horizon_sessions": 20}, "source: required"),
        ({"measure": "lift_pts", "value": 1, "horizon_sessions": 7, "source": 0}, "not one of"),
        ({"measure": "lift_pts", "value": 1, "horizon_sessions": 20, "source": 9}, "not an index"),
        (
            {"measure": "lift_pts", "value": 1, "horizon_sessions": 20, "source": 0, "sample": 0},
            "sample",
        ),
        (
            {"measure": "lift_pts", "value": 1, "horizon_sessions": 20, "source": 0, "x": 1},
            "unknown keys",
        ),
    ],
)
def test_a_published_table_fails_closed(published: dict[str, Any], match: str) -> None:
    with pytest.raises(ConfigurationError, match=match):
        parse(published=published)


def test_family_is_an_optional_catalogue_letter() -> None:
    assert parse_edge(document(), "drift", WHERE).family == ""
    assert parse_edge(document(family="C"), "drift", WHERE).family == "C"
    with pytest.raises(ConfigurationError, match="family"):
        parse_edge(document(family="Z"), "drift", WHERE)


def test_a_published_leg_defaults_from_the_measure_and_fails_closed() -> None:
    base = {"measure": "lift_pts", "value": 4, "horizon_sessions": 20, "source": 0}
    for measure, leg in (
        ("lift_pts", "long"),
        ("mean_excess", "long"),
        ("decile_spread", "long_short"),
    ):
        assert parse(published={**base, "measure": measure}).published.leg == leg  # type: ignore[union-attr]
    assert parse(published={**base, "leg": "long_short"}).published.leg == "long_short"  # type: ignore[union-attr]
    assert parse(published={**base, "leg": "long"}).published == Published(
        "lift_pts", 4.0, 20, 0, None, "long"
    )
    with pytest.raises(ConfigurationError, match="leg"):
        parse(published={**base, "leg": "flat"})


def _calendar(window: str, horizons: list[int], offset: int = 1) -> dict[str, Any]:
    outcome = {
        "kind": "excess_return",
        "horizon_sessions": horizons,
        "benchmark": "SPY",
        "start_offset_sessions": offset,
    }
    return {"schedule": f"calendar:{window}", "outcome": outcome}


def test_a_calendar_schedule_takes_its_window_length_as_the_one_horizon() -> None:
    edge = parse(**_calendar("turn_of_month", [4]))
    assert edge.schedule == "calendar:turn_of_month"
    assert edge.event_class is None
    assert edge.base == "universe"
    assert parse(**_calendar("pre_holiday", [1])).outcome.horizon_sessions == (1,)


@pytest.mark.parametrize(("window", "length"), [("pre_month_end", 3), ("year_turn", 10)])
def test_the_h5_calendar_windows_load_with_their_length_as_the_horizon(
    window: str, length: int
) -> None:
    edge = parse(**_calendar(window, [length]))
    assert edge.schedule == f"calendar:{window}"
    assert edge.outcome.horizon_sessions == (length,)
    with pytest.raises(ConfigurationError, match=f"calendar:{window} is {length} sessions long"):
        parse(**_calendar(window, [length + 1]))


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        (_calendar("turn_of_month", [5]), "calendar:turn_of_month is 4 sessions long"),
        (_calendar("opex_week", [5, 10]), "its one horizon is \\[5\\]"),
        (_calendar("quarter_end", [5], offset=2), "so 1, got 2"),
        ({"schedule": "calendar:fomc"}, "schedule: expected one of"),
    ],
)
def test_a_calendar_schedule_refuses_a_horizon_offset_or_window_that_does_not_fit(
    changes: dict[str, Any], message: str
) -> None:
    with pytest.raises(ConfigurationError, match=message):
        parse(**changes)


def test_a_variant_may_not_change_a_calendar_horizon() -> None:
    variants = [{"id": "long", "outcome": {"horizon_sessions": [20]}}]
    with pytest.raises(ConfigurationError, match="4 sessions long"):
        parse(**_calendar("turn_of_month", [4]), variants=variants)


def test_the_standard_token_is_a_baseline_entry_and_nothing_else() -> None:
    assert parse(baselines=["@standard"]).baselines == ("@standard",)  # expanded on load
    assert parse(baselines=["size_small", "@standard"]).baselines == ("size_small", "@standard")
    with pytest.raises(ConfigurationError, match="invalid screener id"):
        parse(screeners=["@standard"])  # only baselines take it
    with pytest.raises(ConfigurationError, match="invalid screener id"):
        parse(baselines=["@other"])
    with pytest.raises(ConfigurationError, match="listed twice"):
        parse(baselines=["@standard", "@standard"])


def test_expand_baselines_keeps_the_token_place_and_drops_repeats_and_own_screeners() -> None:
    standard = ("size_small", "momentum_12_1", "ivol_high")
    assert expand_baselines(("@standard",), standard, ()) == standard
    assert expand_baselines(("beta_low", "@standard"), standard, ()) == ("beta_low", *standard)
    assert expand_baselines(("@standard", "beta_low"), standard, ()) == (*standard, "beta_low")
    # a decoy already listed, or the edge's own screener, is not run twice
    assert expand_baselines(("ivol_high", "@standard"), standard, ("momentum_12_1",)) == (
        "ivol_high", "size_small",
    )  # fmt: skip
    assert expand_baselines(("size_small",), standard, ()) == ("size_small",)  # no token: as is
    assert expand_baselines((), standard, ()) == ()


def test_an_event_schedule_may_name_a_subtype_of_the_class() -> None:
    e = parse(schedule="on_event:filing_8k:4.02")
    assert (e.event_class, e.event_subtype, e.base) == ("filing_8k", "4.02", "event")
    plain = parse(schedule="on_event:index_change")
    assert (plain.event_class, plain.event_subtype) == ("index_change", None)
    assert parse(schedule="on_event:index_change:deletion").event_subtype == "deletion"
    assert parse(schedule="every_session").event_subtype is None


@pytest.mark.parametrize(
    ("schedule", "message"),
    [
        ("on_event:index_change:sideways", "'sideways' is not a subtype of 'index_change'"),
        ("on_event:nt_late_filing:x", "is not a subtype of 'nt_late_filing' \\(known: none\\)"),
        ("on_event:filing_8k", "needs a subtype, one of"),
        ("on_event:filing_8k:9.99", "'9.99' is not a subtype of 'filing_8k'"),
        ("on_event:insider_buy", "schedule: expected one of"),
    ],
)
def test_an_unknown_or_missing_subtype_fails_closed(schedule: str, message: str) -> None:
    with pytest.raises(ConfigurationError, match=message):
        parse(schedule=schedule)


def test_an_outcome_side_defaults_to_long_and_a_short_or_long_short_names_its_borrow() -> None:
    assert parse().outcome.side == "long" and parse().outcome.borrow_bps_annual is None
    for side in ("short", "long_short"):
        got = parse(top_k=5, outcome=_outcome(side=side, borrow_bps_annual=75)).outcome
        assert (got.side, got.borrow_bps_annual) == (side, 75.0)


def test_a_variant_may_compare_sides_and_is_held_to_the_same_rules() -> None:
    got = parse(
        top_k=5,
        variants=[{"id": "avoid", "outcome": {"side": "short"}}],
    )
    assert [v.outcome.side for v in got.variants] == ["short"]
    with pytest.raises(ConfigurationError, match="a 'short' outcome ranks the names"):
        parse(variants=[{"id": "avoid", "outcome": {"side": "short"}}])  # top_k = "all"


def test_a_long_outcome_hashes_as_it_did_before_sides() -> None:
    """No stored leg or run is recomputed by the arrival of sides: the identity of a long outcome
    has no side key, a short one's has."""
    assert "side" not in identity_dict(asdict(parse().outcome))
    assert (
        "borrow_bps_annual"
        not in identity_dict({"outcomes": [asdict(parse().outcome)]})["outcomes"][0]
    )
    short = parse(top_k=5, outcome=_outcome(side="short")).outcome
    assert identity_dict(asdict(short))["side"] == "short"


def test_every_outcome_side_is_a_column_of_the_results_the_ledger_and_the_legs() -> None:
    """Fitness: the side is stored with every result and ledger row, and a long-short leg's short
    values with its leg (the Guide term of each value: ``tests/architecture/guide``)."""
    assert SIDES == ("long", "short", "long_short")
    for table in (EDGE_EVAL, EDGE_TRADES):
        assert "side" in [c.name for c in table.columns]
    assert "short_values" in [c.name for c in EDGE_LEGS.columns]


def test_a_published_figure_of_a_short_edge_defaults_to_the_short_leg() -> None:
    def leg(measure: str, side: str) -> str:
        got = parse(
            top_k=5,
            outcome=_outcome(side=side),
            sources=[{"title": "A paper"}],
            published={"measure": measure, "value": 0.01, "horizon_sessions": 20, "source": 0},
        )
        assert got.published is not None
        return got.published.leg

    assert leg("mean_excess", "short") == "short"
    assert leg("decile_spread", "short") == "long_short"  # a spread stays a spread
    assert leg("mean_excess", "long") == "long"


def test_an_excess_return_may_name_the_residual_return_measure() -> None:
    outcome = {"kind": "excess_return", "horizon_sessions": [20], "benchmark": "SPY",
               "start_offset_sessions": 1, "measure": "residual_return"}  # fmt: skip
    edge = parse(outcome=outcome, schedule="every_session")
    assert edge.outcome.measure == "residual_return" and edge.outcome.is_return
    plain = {k: v for k, v in outcome.items() if k != "measure"}
    assert parse(outcome=plain, schedule="every_session").outcome.measure is None


@pytest.mark.parametrize("measure", ["excess_return", "realised_to_implied_vol", "nope"])
def test_an_excess_return_refuses_any_other_measure(measure: str) -> None:
    outcome = {"kind": "excess_return", "horizon_sessions": [20], "benchmark": "SPY",
               "start_offset_sessions": 1, "measure": measure}  # fmt: skip
    with pytest.raises(ConfigurationError, match="measure"):
        parse(outcome=outcome, schedule="every_session")


def test_a_hit_target_still_refuses_the_residual_measure() -> None:
    outcome = {
        "kind": "hit_target", "horizon_sessions": [20], "benchmark": "SPY", "target": 0.0,
        "measure": "residual_return", "direction": "above", "start_offset_sessions": 1,
    }  # fmt: skip
    with pytest.raises(ConfigurationError, match="measure"):
        parse(outcome=outcome, schedule="every_session")


def _band(**changes: Any) -> dict[str, Any]:
    """A monthly top-5 edge with a band of 8: the changes override its keys (None drops one)."""
    base = {"schedule": "month_end", "top_k": 5, "outcome": _outcome(hold_rank=8)}
    return {**base, **changes}


def test_a_hold_rank_types_into_the_outcome_of_a_long_or_short_edge() -> None:
    assert parse(**_band()).outcome.hold_rank == 8
    assert parse(**_band(top_k=8)).outcome.hold_rank == 8  # a band of no depth is allowed
    assert parse(**_band(outcome=_outcome(hold_rank=8, side="short"))).outcome.side == "short"
    assert parse(
        **_band(schedule="every_session", outcome=_outcome(hold_rank=6, horizon_sessions=[1]))
    )
    assert parse(**_band(outcome=_outcome())).outcome.hold_rank is None
    variant = {"id": "deep", "outcome": {"hold_rank": 12}}
    assert parse(**_band(variants=[variant])).variants[0].outcome.hold_rank == 12


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"top_k": 9}, "hold_rank: 8 must be an integer >= top_k"),  # hold_rank >= top_k
        ({"top_k": "all"}, "hold_rank: 8 must be an integer >= top_k"),
        ({"outcome": _outcome(hold_rank=0)}, "hold_rank: expected an integer >= 1"),
        ({"outcome": _outcome(hold_rank=2.5)}, "hold_rank: expected an integer >= 1"),
        ({"outcome": _outcome(hold_rank="deep")}, "hold_rank: expected an integer >= 1"),
        ({"outcome": _outcome(hold_rank=8, side="long_short")}, "a long_short spread has no cost"),
        (
            {
                "outcome": {
                    "kind": "hit_target",
                    "horizon_sessions": [20],
                    "benchmark": "SPY",
                    "start_offset_sessions": 1,
                    "target": 0.1,
                    "measure": "excess_return",
                    "direction": "above",
                    "hold_rank": 8,
                }
            },
            "a band is for a long or short excess_return",
        ),
        (
            {"schedule": "every_session"},
            "month_end, or every_session at horizon_sessions = \\[1\\]",
        ),
        ({"schedule": "on_event:earnings_reaction"}, "month_end, or every_session at"),
        (
            {
                "schedule": "calendar:turn_of_month",
                "outcome": _outcome(hold_rank=8, horizon_sessions=[4]),
            },
            "month_end, or every_session at",
        ),
    ],
)
def test_a_hold_rank_is_refused_where_a_position_cannot_carry_over(
    changes: dict[str, Any], message: str
) -> None:
    with pytest.raises(ConfigurationError, match=message):
        parse(**_band(**changes))


def test_a_variant_hold_rank_below_top_k_is_refused() -> None:
    with pytest.raises(ConfigurationError, match="hold_rank: 3 must be an integer >= top_k"):
        parse(**_band(variants=[{"id": "thin", "outcome": {"hold_rank": 3}}]))


def test_an_edge_without_a_hold_rank_hashes_as_it_did_before_bands() -> None:
    """No stored leg, run or trial is recomputed by the arrival of bands: the identity of an
    outcome without one has no key for it, one with one has."""
    assert "hold_rank" not in identity_dict(asdict(parse().outcome))
    assert (
        "hold_rank"
        not in identity_dict({"o": [asdict(parse(**_band(outcome=_outcome())).outcome)]})["o"][0]
    )
    assert identity_dict(asdict(parse(**_band()).outcome))["hold_rank"] == 8


def test_every_shipped_edge_with_a_band_keeps_it_at_or_below_top_k() -> None:
    """Fitness: a site edge document that names a ``hold_rank`` parses (so it holds down from its
    ``top_k``, on a schedule whose positions carry over)."""
    root = Path(__file__).resolve().parents[4] / "config" / "site" / "edges"
    for path in sorted(root.glob("*/edge.toml")):
        if "hold_rank" in path.read_text():
            doc = tomllib.loads(path.read_text())
            got = parse_edge(doc, path.parent.name, str(path))
            assert got.outcome.hold_rank is None or got.top_k is not None
            assert got.outcome.hold_rank is None or got.outcome.hold_rank >= (got.top_k or 0)


def _pair(**changes: Any) -> dict[str, Any]:
    base = {"kind": "pair_spread", "benchmark": "none"}
    return _outcome(**{"pair_field": "rollup.share_classes@v1.sibling_id", **base, **changes})


def test_a_pair_spread_names_its_pair_field_and_the_borrow_of_the_rich_leg() -> None:
    got = parse(top_k=5, outcome=_pair(borrow_bps_annual=60, cost_bps=10)).outcome
    assert got.kind == "pair_spread" and got.pair_field == "rollup.share_classes@v1.sibling_id"
    assert got.borrow_bps_annual == 60.0 and got.side == "long"
    assert got.result_side == "long_short"  # judged as a spread: a diagnostic, never a basis
    assert parse().outcome.result_side == "long" and parse().outcome.pair_field is None


@pytest.mark.parametrize(
    ("outcome", "message"),
    [
        (_pair(pair_field=None), "pair_field: required"),
        (_pair(benchmark="SPY"), "needs benchmark = 'none'"),
        (_pair(side="short"), "needs an excess_return outcome"),
        (_pair(max_drawdown=0.2), "needs benchmark = 'none'"),
        (_outcome(pair_field="rollup.share_classes@v1.sibling_id"), "only a pair_spread"),
        (_outcome(borrow_bps_annual=50), "only a short leg pays borrow"),
    ],
)
def test_a_pair_spread_is_refused_what_a_two_leg_spread_cannot_be(
    outcome: dict[str, Any], message: str
) -> None:
    with pytest.raises(ConfigurationError, match=message):
        parse(top_k=5, outcome=outcome)


def test_a_document_with_no_pair_field_hashes_as_it_did_before_pairs() -> None:
    """No stored leg or run is recomputed by the arrival of pair_field: its identity has no key
    for it unless it is set."""
    assert "pair_field" not in identity_dict(asdict(parse().outcome))
    pair = parse(top_k=5, outcome=_pair()).outcome
    assert identity_dict(asdict(pair))["pair_field"] == "rollup.share_classes@v1.sibling_id"
