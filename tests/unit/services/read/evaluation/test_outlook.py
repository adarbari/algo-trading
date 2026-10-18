"""``EdgeOutlook`` (what would change the verdict) and the haircut Sharpe ratio on the verdict."""

import math
from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from algotrade.services.read.evaluation.evidence import (
    BEYOND_PROJECTION,
    NOT_STORED,
    OOS_HIDDEN,
    PROJECTED,
    UNPROJECTABLE,
)
from algotrade.services.read.evaluation.verdict import EdgeFacts, counts_wins, judge
from tests.unit.services.read.evaluation.test_verdict import SPLIT, T, draws, result, verdict


def outlook(rows, **facts):  # type: ignore[no-untyped-def]
    v = judge("e", rows, SPLIT, T, facts=EdgeFacts(**facts))
    assert v.evidence is not None
    return v.evidence.outlook


def test_too_few_oos_trades_is_a_count_with_what_is_missing() -> None:
    o = outlook(result(oos={"sessions": 12}), schedule="every_session")
    assert o is not None
    assert (o.criterion, o.level, o.have, o.needed, o.remaining) == (
        "trades",
        "promising",
        12,
        40,
        28,
    )
    assert o.sentence == "Promising needs 40 out-of-sample trades: 12 so far, 28 to go."
    assert o.projection_state == NOT_STORED  # no run stores the schedule's exits yet


def test_an_event_schedule_cannot_be_projected_and_a_hidden_copy_says_so() -> None:
    rows = result(oos={"sessions": 12})
    event = outlook(rows, schedule="on_event:earnings_reaction")
    hidden = outlook(rows, schedule="on_event:earnings_reaction", hidden=True)
    assert event is not None and event.projection_state == UNPROJECTABLE
    assert hidden is not None and hidden.projection_state == OOS_HIDDEN  # hidden wins


EXITS = tuple(date(2027, 1, 4) + timedelta(days=i) for i in range(60))  # one per day, in order


def stored(**counts: object) -> dict[str, object]:
    """The basis's ``all`` row as the harness writes it (ADR 0064 decision 7)."""
    return {
        "projected_exits": EXITS, "decisions_scheduled": 20, "decisions_measured": 20,
        "decisions_scheduled_oos": 10, "decisions_measured_oos": 10, **counts,
    }  # fmt: skip


def test_a_stored_projection_gives_the_exit_of_the_missing_trades() -> None:
    o = outlook(result(oos={"sessions": 12}, whole=stored()), schedule="every_session")
    assert o is not None and o.remaining == 28
    assert (o.projection_state, o.fill_ratio) == (PROJECTED, 1.0)
    assert o.expected_by == EXITS[27]  # the 28th stored exit: every decision session measured


def test_the_expected_exit_is_scaled_by_how_often_the_out_of_sample_side_fills() -> None:
    half = outlook(result(oos={"sessions": 30}, whole=stored(decisions_measured_oos=5)))
    assert half is not None and (half.remaining, half.fill_ratio) == (10, 0.5)
    assert half.expected_by == EXITS[19]  # ceil(10 / 0.5) = 20th exit


def test_the_fill_ratio_is_floored_and_a_run_with_no_split_uses_the_whole_run() -> None:
    dead = outlook(result(oos={"sessions": 38}, whole=stored(decisions_measured_oos=0)))
    assert dead is not None and dead.fill_ratio == 0.25 and dead.expected_by == EXITS[7]
    whole = outlook(
        result(
            oos={"sessions": 30},
            whole=stored(decisions_scheduled_oos=None, decisions_measured_oos=None,
                         decisions_measured=15),
        )
    )  # fmt: skip
    assert whole is not None and whole.fill_ratio == 0.75 and whole.expected_by == EXITS[13]


def test_a_count_past_the_stored_list_is_beyond_the_projection() -> None:
    last = outlook(result(oos={"sessions": 12}, whole=stored(decisions_measured_oos=5)))
    assert last is not None and last.projection_state == PROJECTED  # ceil(28 / 0.5) = 56 of 60
    assert last.expected_by == EXITS[55]
    far = outlook(result(oos={"sessions": 12}, whole=stored(decisions_measured_oos=3)))
    assert far is not None and far.projection_state == BEYOND_PROJECTION  # ceil(28 / 0.3) = 94
    assert far.expected_by is None and far.fill_ratio == 0.3


def test_exits_without_the_counts_or_the_counts_without_exits_are_not_stored() -> None:
    no_counts = outlook(result(oos={"sessions": 12}, whole=stored(decisions_scheduled=None,
                        decisions_scheduled_oos=None)))  # fmt: skip
    no_exits = outlook(result(oos={"sessions": 12}, whole=stored(projected_exits=())))
    assert no_counts is not None and no_counts.projection_state == NOT_STORED
    assert no_exits is not None and no_exits.projection_state == NOT_STORED
    assert no_counts.expected_by is None and no_exits.fill_ratio is None


def test_an_event_schedule_and_a_hidden_copy_are_never_projected_even_with_exits() -> None:
    rows = result(oos={"sessions": 12}, whole=stored())
    event = outlook(rows, schedule="on_event:earnings_reaction")
    hidden = outlook(rows, schedule="every_session", hidden=True)
    assert event is not None and event.projection_state == UNPROJECTABLE
    assert hidden is not None and hidden.projection_state == OOS_HIDDEN
    assert event.expected_by is None and hidden.expected_by is None


def test_a_promising_edge_waits_on_works_counts_the_further_side_first() -> None:
    o = outlook(result(oos={"sessions": 40}, whole={"sessions": 70}))
    assert o is not None and o.criterion == "works_trades" and o.level == "works"
    assert (o.have, o.needed, o.remaining) == (70, 100, 30)  # the whole history is further off
    far_oos = outlook(result(oos={"sessions": 41}, whole={"sessions": 130}), schedule="month_end")
    assert far_oos is not None and far_oos.criterion == "works_t"  # both counts reached


def test_a_test_that_is_not_a_count_has_no_projection() -> None:
    o = outlook(result(oos={"sessions": 60, "decile_t": 1.5}))
    assert o is not None and o.criterion == "decile_t"
    assert (o.have, o.needed, o.remaining, o.projection_state) == (None, None, None, None)
    assert "decile t" in o.sentence


def test_a_missing_figure_is_the_gap_in_words() -> None:
    o = outlook(result(oos={"sessions": 60, "decile_t": None}))
    assert o is not None and o.sentence.endswith("is not measured yet")


def test_works_and_waiting_have_no_outlook() -> None:
    strong = result(
        oos={"decile_t": 3.0, "decile_spread": 0.9},
        whole={"sessions": 100, "deflated_sharpe": 0.95, "pbo": 0.2},
    )
    works = judge("e", strong, SPLIT, T, draws=draws(100))
    assert works.verdict == "works" and works.evidence is not None
    assert works.evidence.outlook is None
    assert verdict(None).evidence is None


def test_the_haircut_is_the_stored_sharpe_after_the_variants_tried() -> None:
    v = verdict(result(whole={"sessions": 70, "sharpe": 0.4, "trials": 5}))
    h = v.haircut
    assert h is not None
    assert (h.sharpe, h.trials, h.sessions, h.method) == (0.4, 5, 70, "bonferroni")
    t = 0.4 * math.sqrt(70)
    p = 5 * math.erfc(t / math.sqrt(2.0))
    assert math.erfc(h.haircut_sharpe * math.sqrt(70) / math.sqrt(2.0)) == pytest.approx(p)
    assert h.cut == pytest.approx(1 - h.haircut_sharpe / 0.4)
    words = (
        f"falls to {h.haircut_sharpe:.2f} after 5 variants tried, a haircut of {h.cut * 100:.0f}%."
    )
    assert h.summary == f"A Sharpe ratio of 0.40 per decision session {words}"


def test_a_win_rate_outcomes_haircut_says_its_sharpe_is_of_the_win_rate_above_the_base() -> None:
    """ADR 0064 amendment 2026-10-11: a cushion or ratio outcome's stored Sharpe ratio is of the
    session's excess wins, per decision session, and the sentence says which series it is."""
    rows = result(whole={"sessions": 70, "sharpe": 0.4, "trials": 5})
    h = judge("e", rows, SPLIT, T, facts=EdgeFacts(wins=True)).haircut
    assert h is not None and h.summary.startswith(
        "A Sharpe ratio of 0.40 per decision session, of the win rate above the base rate, falls to"
    )
    assert "per trade" not in h.summary


@pytest.mark.parametrize(("applies", "wins"), [(True, False), (False, True), (None, False)])
def test_an_edge_counts_wins_when_its_outcome_is_not_a_return(
    applies: bool | None, wins: bool
) -> None:
    settings = None if applies is None else SimpleNamespace(cost_applies=applies, kind="hit_target")
    assert counts_wins(SimpleNamespace(settings=settings)) is wins  # type: ignore[arg-type]


def test_a_model_pnl_edge_never_counts_wins_though_no_round_trip_cost_grid_applies() -> None:
    settings = SimpleNamespace(cost_applies=False, kind="option_model_pnl")
    assert counts_wins(SimpleNamespace(settings=settings)) is False  # type: ignore[arg-type]


@pytest.mark.parametrize("over", [{"sharpe": None}, {"trials": None}, {"sharpe": -0.1}])
def test_no_haircut_without_a_positive_sharpe_and_the_trials(over: dict[str, object]) -> None:
    assert (
        verdict(result(whole={"sessions": 70, "sharpe": 0.4, "trials": 5, **over})).haircut is None
    )


def test_the_haircut_counts_the_sessions_the_series_measured_with_picks() -> None:
    rows = result(whole={"sessions": 70, "sharpe": 0.4, "trials": 5})
    series = EdgeFacts(measured=lambda: {("scr", 20): 50})
    h = judge("e", rows, SPLIT, T, facts=series).haircut
    assert h is not None and h.sessions == 50  # not the stored 70
    t = 0.4 * math.sqrt(50)
    p = 5 * math.erfc(t / math.sqrt(2.0))
    assert math.erfc(h.haircut_sharpe * math.sqrt(50) / math.sqrt(2.0)) == pytest.approx(p)


def test_a_run_with_no_series_keeps_the_stored_count_and_an_empty_series_has_no_haircut() -> None:
    rows = result(whole={"sessions": 70, "sharpe": 0.4, "trials": 5})
    older = judge("e", rows, SPLIT, T, facts=EdgeFacts(measured=lambda: None)).haircut
    assert older is not None and older.sessions == 70
    nothing = judge("e", rows, SPLIT, T, facts=EdgeFacts(measured=lambda: {}))
    assert nothing.haircut is None  # the series measured no session with picks: no n, no haircut


def test_the_series_is_read_only_when_there_is_a_sharpe_to_cut() -> None:
    calls: list[int] = []

    def counted() -> dict[tuple[str, int], int]:
        calls.append(1)
        return {}

    judge("e", result(whole={"sharpe": None}), SPLIT, T, facts=EdgeFacts(measured=counted))
    assert calls == []


WEEKLY = tuple(date(2027, 1, 4) + timedelta(weeks=i) for i in range(1, 60))  # Mondays, 5 sessions


def test_the_sentence_names_the_date_and_the_cadence_of_the_stored_exits() -> None:
    o = outlook(result(oos={"sessions": 12}, whole=stored(projected_exits=WEEKLY)))
    assert o is not None and o.cadence_sessions == 5
    assert o.expected_by == WEEKLY[27]
    assert o.sentence == (
        f"Promising needs 40 out-of-sample trades: 12 so far, 28 to go, "
        f"about {WEEKLY[27]:%b %Y} at one trade every 5 sessions."
    )
    daily = outlook(result(oos={"sessions": 12}, whole=stored()))
    assert daily is not None and daily.sentence.endswith("at one trade every session.")


def test_both_counts_are_projected_not_only_the_first_failing_one() -> None:
    o = outlook(result(oos={"sessions": 12}, whole={"sessions": 70, **stored()}))
    assert o is not None and o.criterion == "trades"
    by = {p.criterion: p for p in o.projections}
    assert set(by) == {"trades", "works_trades"}
    assert (by["trades"].remaining, by["trades"].expected_by) == (28, EXITS[27])
    assert (by["works_trades"].remaining, by["works_trades"].needed) == (30, 100)
    assert by["works_trades"].expected_by == EXITS[29] and by["works_trades"].state == PROJECTED
    # a count already reached is not projected
    done = outlook(
        result(oos={"sessions": 45, "decile_t": 1.5}, whole={"sessions": 70, **stored()})
    )
    assert done is not None and [p.criterion for p in done.projections] == ["works_trades"]


def test_the_next_close_is_the_first_stored_exit_after_the_run() -> None:
    rows = result(oos={"sessions": 12}, whole=stored())
    o = outlook(rows)
    assert o is not None and o.next_close == EXITS[0]
    late = outlook(rows, after=EXITS[2])
    assert late is not None and late.next_close == EXITS[3]
    assert outlook(rows, hidden=True).next_close is None  # type: ignore[union-attr]
    bare = outlook(result(oos={"sessions": 12}))
    assert bare is not None and bare.next_close is None  # not stored: never made up


def test_at_the_count_the_verdict_on_todays_figures_with_its_reasons() -> None:
    weak = result(oos={"sessions": 12, "decile_t": 0.4}, whole={"deflated_sharpe": 0.1})
    o = outlook(weak)
    assert o is not None and o.at_target is not None
    assert (o.at_target.needed, o.at_target.level) == (40, "not_working")
    assert o.at_target.reasons == (
        "Top vs bottom decile t is 0.40; it needs at least 2",
        "Deflated Sharpe is 0.10; it needs at least 0.8",
    )
    assert o.at_target.sentence == (
        "At 40, on today's figures: Not working. Top vs bottom decile t is 0.40; it needs at "
        "least 2 \u00b7 Deflated Sharpe is 0.10; it needs at least 0.8."
    )
    good = outlook(result(oos={"sessions": 12}))
    assert good is not None and good.at_target is not None and good.at_target.level == "promising"
    # the verdict itself is unchanged by what the outlook computes
    assert verdict(weak).verdict == "not_enough_data"


def test_a_test_that_is_not_a_count_has_no_at_target_but_still_the_dates() -> None:
    o = outlook(result(oos={"sessions": 60, "decile_t": 1.5}, whole=stored()))
    assert o is not None and o.at_target is None and o.criterion == "decile_t"
    assert o.next_close == EXITS[0] and [p.criterion for p in o.projections] == ["works_trades"]
    assert outlook(result(oos={"sessions": 12}), hidden=True).at_target is None  # type: ignore[union-attr]
