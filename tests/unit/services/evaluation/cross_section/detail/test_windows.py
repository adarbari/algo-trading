"""The calendar facts of the measured blocks (ADR 0064 decisions 1 and 7): the unit of a value,
the number of decision sessions to project, and the exits of the schedule's next decision
sessions."""

from datetime import date

from algotrade.config.edges.verdict import VerdictSettings
from algotrade.core.time.calendar import next_session, sessions_between
from algotrade.services.evaluation.cross_section.detail.windows import (
    exit_session,
    next_exits,
    plan_exits,
    projection_count,
    unit_of,
)
from algotrade.services.evaluation.cross_section.sessions import Leg
from tests.unit.services.evaluation.cross_section.conftest import edge

START = date(2026, 9, 1)


def test_the_unit_follows_the_outcome() -> None:
    assert unit_of(edge()) == "excess_return"
    base = {"kind": "hit_target", "horizon_sessions": [2], "start_offset_sessions": 1,
            "direction": "above", "target": 0.05}  # fmt: skip
    none = {**base, "benchmark": "none", "measure": "excess_return"}
    assert unit_of(edge(outcome=none)) == "return"
    assert unit_of(edge(outcome={**none, "benchmark": "SPY"})) == "excess_return"
    ratio = {**base, "benchmark": "none", "measure": "realised_to_implied_vol"}
    assert unit_of(edge(outcome=ratio)) == "ratio"
    otm = {**base, "kind": "expires_otm", "benchmark": "none", "structure": "put",
           "otm_pct": 0.1, "iv_field": "feature.x"}  # fmt: skip
    otm = {k: v for k, v in otm.items() if k not in ("direction", "target")}
    assert unit_of(edge(outcome=otm)) == "cushion"


def test_n_is_the_largest_count_a_criterion_asks_of_a_quarter_fill() -> None:
    assert projection_count(VerdictSettings()) == 400  # 100 / 0.25
    assert projection_count(VerdictSettings(works_trades=10, min_oos_trades=60)) == 240


def test_the_next_exits_are_the_schedule_s_decisions_a_horizon_apart() -> None:
    exits = next_exits("every_session", 1, 3, START, None, 4)
    days = sessions_between(START, date(2026, 12, 31))
    decisions = days[::3][:4]
    assert exits == tuple(exit_session(next_session(d), 3) for d in decisions)
    after = exits[1]
    assert next_exits("every_session", 1, 3, START, after, 2) == exits[2:4]


def test_a_schedule_is_extended_until_it_holds_n_decisions_years_ahead() -> None:
    exits = next_exits("month_end", 1, 21, START, None, 100)
    assert len(exits) == 100 and exits[-1].year >= 2034  # one a month: eight years at least


def test_an_event_schedule_has_no_projection_and_a_calendar_one_skips_the_measured() -> None:
    legs = [[Leg(START, next_session(START))]]
    kept, exits = plan_exits(edge(schedule="month_end"), legs, {next_session(START)}, 2, START, 3)
    assert kept == legs and exits is not None and exits[0] > exit_session(next_session(START), 2)
    assert plan_exits(edge(schedule="on_event:earnings_reaction"), legs, set(), 2, START, 3) == (
        [],
        None,
    )


def test_n_exits_are_stored_even_at_a_long_horizon_far_from_the_range_start() -> None:
    exits = next_exits("every_session", 1, 60, START, None, 400)
    assert len(exits) == 400  # 400 x 60 sessions is about 96 years: no fixed bound from START
    late = next_exits("every_session", 1, 60, START, date(2060, 1, 1), 400)
    assert len(late) == 400 and late[0] > date(2060, 1, 1)
