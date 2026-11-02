"""The gate decision (ADR 0088): a two-rule setup gate and a screener's ``pause_in`` decided by
one pure function, UNKNOWN never open."""

import pytest

from algotrade.core.model.predicates import Group, Rule
from algotrade.engines.screening.gate import (
    CLOSED,
    LABEL,
    OPEN,
    UNDECIDED,
    RegimeGate,
    decide_gate,
    pause_group,
)

CONTANGO, FOMC = (
    "market.market_conditions@v1.vix_contango_on",
    "market.market_conditions@v1.sessions_to_fomc",
)
GATE = Group("all", (Rule(CONTANGO, "eq", True), Rule(FOMC, "gt", 2)))


@pytest.mark.parametrize(
    ("row", "state"),
    [
        ({CONTANGO: True, FOMC: 5.0}, OPEN),
        ({CONTANGO: False, FOMC: 5.0}, CLOSED),
        ({CONTANGO: True, FOMC: 1.0}, CLOSED),
        ({CONTANGO: True, FOMC: None}, UNDECIDED),  # the schedule is not known: never open
        ({CONTANGO: True, FOMC: float("nan")}, UNDECIDED),
        ({CONTANGO: False, FOMC: None}, CLOSED),  # a FALSE rule decides: closed beats unknown
        ({}, UNDECIDED),
    ],
)
def test_a_two_rule_gate_decides_open_closed_or_unknown(row, state) -> None:
    assert decide_gate(GATE, row).state == state


def test_the_reason_names_the_first_failing_rule_by_term_and_never_a_value() -> None:
    closed = decide_gate(GATE, {CONTANGO: True, FOMC: 1.0}, term=lambda f: f.rsplit(".", 1)[1])
    assert closed.reason == "sessions_to_fomc not met"
    unknown = decide_gate(GATE, {CONTANGO: True, FOMC: None})
    assert unknown.reason == f"{FOMC} not known"


def test_a_label_outside_the_declared_domain_is_unknown_for_an_edge_gate() -> None:
    label = "market.regime@v3.label"
    group = Group("all", (Rule(label, "not_in", ("STRESS", "CRISIS")),))
    domains = {label: ("CALM", "CAUTION", "STRESS", "CRISIS")}
    assert decide_gate(group, {label: "FOO"}, domains).state == UNDECIDED
    assert decide_gate(group, {label: "CALM"}, domains).state == OPEN
    assert decide_gate(group, {label: "STRESS"}, domains).state == CLOSED


def _gate(label, pause=frozenset({"STRESS", "CRISIS"})) -> RegimeGate:
    known = {"CALM": 1.0, "CAUTION": 0.75, "STRESS": 0.5, "CRISIS": 0.25}
    return RegimeGate("vrp", label, known, pause)


def test_pause_in_is_the_same_decision() -> None:
    assert decide_gate(pause_group(frozenset({"STRESS"})), {LABEL: "CALM"}).state == OPEN
    assert _gate("CALM").reason is None
    assert _gate("STRESS").reason == "regime=STRESS: vrp pauses in STRESS"
    assert _gate("FOO").reason == "regime unknown"  # not a known label: unknown, never open
    assert _gate(None).reason == "regime unknown"
    assert _gate(None, frozenset()).reason is None  # a screener that pauses nowhere is ungated
