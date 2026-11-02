"""The position key (ADR 0088, G24): built from the resolved legs and parameters, never the
template's id; round-trips to its spec; two exit rules (or a different hold) are two keys; a
template edit changes the key a trade is stored under."""

from dataclasses import asdict, replace
from datetime import date
from typing import Any

import pytest

from algotrade.config.edges.document import parse_edge
from algotrade.config.edges.identity import identity_dict
from algotrade.config.edges.positions.cases import Case, CaseValue
from algotrade.config.edges.positions.key import (
    case_point,
    case_points,
    grid_outcomes,
    key_of,
    parse_position_key,
    parsed_key,
    position_key,
    resolve_legs,
    share_position_key,
    with_legs,
)
from algotrade.config.edges.positions.spec import ExitRule, ExitSettings
from algotrade.config.edges.positions.templates import load_templates
from algotrade.core.model.errors import ConfigurationError
from algotrade.core.model.predicates import Group, Rule
from algotrade.services.evaluation.forward.settle import outcome_hash
from algotrade.storage.configs.files import FileConfigStore
from tests.conftest import REPO_ROOT
from tests.unit.config.edges.test_document import WHERE, document

TEMPLATES = load_templates(FileConfigStore(REPO_ROOT / "config"))
PUT = {
    "kind": "option_pnl", "horizon_sessions": [21], "benchmark": "none",
    "start_offset_sessions": 1, "tenor_days": 30, "position": "put_spread", "strike_delta": 0.2,
    "expiry_cycle": "weekly", "exit": {"take_profit": 0.5, "stop_loss": 2.0},
}  # fmt: skip


def outcome(**changes: Any) -> Any:
    body = {k: v for k, v in {**PUT, **changes}.items() if v is not None}
    edge = parse_edge(document(schedule="every_session", outcome=body), "drift", WHERE)
    return with_legs(edge, TEMPLATES).outcome


def test_strike_delta_replaces_the_short_delta_leg_only_and_a_wing_keeps_its_delta() -> None:
    legs = outcome().position.legs
    assert [(leg.qty, leg.delta, leg.tenor_days) for leg in legs] == [(-1, 0.2, 30), (1, 0.1, 30)]
    plain = resolve_legs(outcome(strike_delta=None), TEMPLATES["put_spread"])
    assert [leg.delta for leg in plain] == [0.3, 0.1]


def test_the_key_round_trips_to_its_spec() -> None:
    o = outcome()
    key = position_key(o, 21)
    parsed = parse_position_key(key)
    assert parsed == parsed_key(o, 21) and key_of(parsed) == key
    assert parsed.hold == 21 and parsed.collateral == "max_loss" and parsed.offset == 1
    assert [x.kind for x in parsed.exits] == ["TAKE_PROFIT", "STOP_LOSS"]
    with pytest.raises(ConfigurationError, match="not a position key"):
        parse_position_key("{}")


def test_two_exit_rules_or_holds_are_two_keys() -> None:
    a = position_key(outcome(), 21)
    assert a != position_key(outcome(exit={"take_profit": 0.6, "stop_loss": 2.0}), 21)
    assert a != position_key(outcome(), 10)
    assert a == position_key(outcome(), 21)


def test_the_key_never_names_the_template_and_a_template_edit_changes_it() -> None:
    o = outcome()
    assert "put_spread" not in position_key(o, 21)
    spec = o.position
    wider = replace(
        TEMPLATES["put_spread"],
        legs=(
            TEMPLATES["put_spread"].legs[0],
            replace(TEMPLATES["put_spread"].legs[1], delta=0.05),
        ),
    )
    edited = replace(o, position=replace(spec, legs=resolve_legs(o, wider)))
    assert position_key(edited, 21) != position_key(o, 21)


def test_a_template_edit_keeping_its_id_changes_the_edges_identity_and_outcome_hash() -> None:
    body = {k: v for k, v in PUT.items() if v is not None}
    edge = with_legs(
        parse_edge(document(schedule="every_session", outcome=body), "drift", WHERE), TEMPLATES
    )
    wing = TEMPLATES["put_spread"].legs[1]
    edited = {
        **TEMPLATES,
        "put_spread": replace(
            TEMPLATES["put_spread"],
            legs=(TEMPLATES["put_spread"].legs[0], replace(wing, delta=0.05)),
            collateral="cash_secured",
        ),
    }
    again = with_legs(
        parse_edge(document(schedule="every_session", outcome=body), "drift", WHERE), edited
    )
    assert identity_dict(asdict(again.outcome)) != identity_dict(asdict(edge.outcome))
    assert outcome_hash(again) != outcome_hash(edge)


def test_a_case_value_of_zero_is_a_rule_not_the_absence_of_one() -> None:
    o = outcome()
    spec = replace(
        o.position,
        cases=(CaseValue("exit_dte", (Case(Group("all", (Rule("a", "gt", 1),)), 5),), 0),),
    )
    points = case_points(replace(o, position=spec), TEMPLATES)
    dte = [x for p in points for x in parsed_key(p, 21).exits if x.kind == "EXIT_DTE"]
    assert sorted(x.rule.children[0].value for x in dte) == [0, 5]  # type: ignore[union-attr]


def test_one_spelling_per_value_numbers_as_floats_and_dates_as_text() -> None:
    base = parsed_key(outcome(), 21)

    def keyed(value: object) -> str:
        rule = ExitRule("CONDITION", Group("all", (Rule("market.x", "lt", value),)))  # type: ignore[arg-type]
        return key_of(replace(base, exits=(rule,)))

    assert keyed(1) == keyed(1.0)
    assert keyed(date(2026, 1, 1)) == keyed("2026-01-01")  # a date does not crash the dump


def test_the_writer_stores_every_combination_a_name_can_resolve_to() -> None:
    o = outcome()
    high = Group("all", (Rule("a", "gt", 1),))
    cases = (
        CaseValue("tenor_days", (Case(high, 30),), 45),
        CaseValue("exit_dte", (Case(high, 5),), 0),
    )
    case_valued = replace(o, position=replace(o.position, cases=cases))
    points = case_points(case_valued, TEMPLATES)
    keys = {position_key(p, 21) for p in points}
    assert len(keys) == 4  # (45, 0), (45, 5), (30, 0), (30, 5): both cases off their defaults too
    assert position_key(case_point(case_valued, (30, 5), TEMPLATES), 21) in keys


def test_each_grid_point_is_the_edges_outcome_with_its_values_and_legs_resolved_again() -> None:
    edge = with_legs(
        parse_edge(
            document(
                schedule="every_session", outcome=PUT,
                variant_grid=[{"prefix": "g", "strike_delta": [0.15, 0.25], "take_profit": [0.5]}],
            ),
            "drift", WHERE,
        ),
        TEMPLATES,
    )  # fmt: skip
    points = grid_outcomes(edge, TEMPLATES)
    assert [p for p, _ in points] == ["g_d15_tp50", "g_d25_tp50"]
    assert [o.position.legs[0].delta for _, o in points] == [0.15, 0.25]  # the wing keeps 0.1
    assert {o.position.exit.take_profit for _, o in points} == {0.5}
    keys = {position_key(o, 21) for _, o in points} | {position_key(edge.outcome, 21)}
    assert len(keys) == 3
    assert grid_outcomes(replace(edge, variant_grid=()), TEMPLATES) == ()


def test_a_share_key_holds_its_sides_exit_rules_and_no_option_parameters() -> None:
    share = {"kind": "excess_return", "horizon_sessions": [5], "benchmark": "SPY",
             "start_offset_sessions": 1, "position": "short_shares", "side": "short"}  # fmt: skip
    edge = parse_edge(document(schedule="every_session", outcome=share, top_k=10), "drift", WHERE)
    o = with_legs(edge, TEMPLATES).outcome
    spec = replace(o.position, exit=ExitSettings(take_profit=0.1, stop_loss=0.05))
    parsed = parse_position_key(share_position_key(replace(o, position=spec), 5))
    assert (parsed.hold, parsed.offset, parsed.tenor_days, parsed.expiry_cycle) == (5, 1, None, "")
    assert [leg.kind for leg in parsed.legs] == ["shares"]
    # a short's take profit is a fall of the entry price, its stop a rise
    rules = [(x.kind, x.rule.rules()[0].op, x.rule.rules()[0].value) for x in parsed.exits]
    assert rules == [("TAKE_PROFIT", "lte", -0.1), ("STOP_LOSS", "gte", 0.05)]
    with pytest.raises(ConfigurationError, match="share legs"):
        share_position_key(outcome(), 21)  # an option position has no share key


def test_a_grid_point_of_a_case_valued_outcome_keys_its_own_case_points() -> None:
    high = Group("all", (Rule("a", "gt", 1),))
    body = {**PUT, "tenor_days": {"cases": [{"when": {"all": [{"field": "a", "op": "gt",
                                                               "value": 1}]}, "value": 45}],
                                  "default": 30}}  # fmt: skip
    edge = with_legs(
        parse_edge(
            document(schedule="every_session", outcome=body,
                     variant_grid=[{"prefix": "g", "strike_delta": [0.15]}]),
            "drift", WHERE,
        ),
        TEMPLATES,
    )  # fmt: skip
    ((_, point),) = grid_outcomes(edge, TEMPLATES)
    assert point.position is not None and point.position.cases[0].cases[0].when == high
    own = {
        position_key(p, h) for p in case_points(point, TEMPLATES) for h in point.horizon_sessions
    }
    assert {key for _, _, key in point.position.points} == own  # not the 0.25-delta base's
