"""``EdgeOutlook`` (what would change the verdict) and the haircut Sharpe ratio on the verdict."""

import math

import pytest

from algotrade.services.read.evaluation.evidence import (
    NOT_STORED,
    OOS_HIDDEN,
    UNPROJECTABLE,
)
from algotrade.services.read.evaluation.verdict import EdgeFacts, judge
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
    assert o.sentence == "Out-of-sample trades is 12; it needs at least 40"
    assert o.projection_state == NOT_STORED  # no run stores the schedule's exits yet


def test_an_event_schedule_cannot_be_projected_and_a_hidden_copy_says_so() -> None:
    rows = result(oos={"sessions": 12})
    event = outlook(rows, schedule="on_event:earnings_reaction")
    hidden = outlook(rows, schedule="on_event:earnings_reaction", hidden=True)
    assert event is not None and event.projection_state == UNPROJECTABLE
    assert hidden is not None and hidden.projection_state == OOS_HIDDEN  # hidden wins


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
    assert h.summary == f"A Sharpe ratio of 0.40 per trade {words}"


@pytest.mark.parametrize("over", [{"sharpe": None}, {"trials": None}, {"sharpe": -0.1}])
def test_no_haircut_without_a_positive_sharpe_and_the_trials(over: dict[str, object]) -> None:
    assert (
        verdict(result(whole={"sessions": 70, "sharpe": 0.4, "trials": 5, **over})).haircut is None
    )
