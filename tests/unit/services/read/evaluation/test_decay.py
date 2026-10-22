"""``EdgeDecay``: the paper's figure against the in- and out-of-sample ones of one statistic."""

from dataclasses import replace

import pytest

from algotrade.services.read.evaluation.decay import (
    MEASURED,
    NOT_COMPARABLE,
    NOT_GIVEN,
    NOT_STORED,
    OOS_HIDDEN,
    POINTS,
    RETURN,
    decay_of,
)
from algotrade.services.read.evaluation.edges import EdgePublished, EdgeSource
from algotrade.services.read.evaluation.verdict import EdgeFacts, judge
from tests.unit.services.read.evaluation.verdict.test_judge import SPLIT, T, result, row

SOURCE = EdgeSource("Jegadeesh and Titman, 1993", "https://example.org/jt")


def published(measure: str = "decile_spread", horizon: int = 20, value: float = 0.0131):
    return EdgePublished(measure, value, horizon, SOURCE, 25)


def bars(measure: str, **over: object):
    rows = result(
        oos={"decile_sessions": 11, "decile_spread": 0.02, "mean_excess_picks": 0.004, **over},
        insample={"decile_sessions": 30, "decile_spread": 0.05, "mean_excess_picks": 0.012},
    )
    v = judge("e", rows, SPLIT, T, facts=EdgeFacts(published(measure)))
    assert v.decay is not None
    return {b.period: b for b in v.decay.bars}


def test_a_decile_spread_is_read_with_its_decile_sessions() -> None:
    b = bars("decile_spread")
    assert (b["published"].value, b["published"].n, b["published"].state) == (
        0.0131,
        None,
        MEASURED,
    )
    assert (b["in_sample"].value, b["in_sample"].n) == (0.05, 30)
    assert (b["out_of_sample"].value, b["out_of_sample"].n) == (0.02, 11)


def test_a_mean_excess_and_a_lift_are_read_with_the_trades() -> None:
    mean = bars("mean_excess")
    assert (mean["in_sample"].value, mean["in_sample"].n) == (0.012, 60)
    assert (mean["out_of_sample"].value, mean["out_of_sample"].n) == (0.004, 60)
    lift = bars("lift_pts")
    assert lift["out_of_sample"].value == pytest.approx(10.0)  # 0.60 against 0.50, in points


def test_the_unit_is_points_for_a_lift_and_a_return_otherwise() -> None:
    rows = result()
    for measure, unit in (("lift_pts", POINTS), ("decile_spread", RETURN), ("mean_excess", RETURN)):
        d = judge("e", rows, SPLIT, T, facts=EdgeFacts(published(measure))).decay
        assert d is not None and d.unit == unit and d.measure == measure


def test_a_horizon_that_is_not_the_papers_is_not_comparable() -> None:
    d = judge("e", result(), SPLIT, T, facts=EdgeFacts(published(horizon=60))).decay
    assert d is not None and d.basis_horizon == 20
    states = {b.period: b.state for b in d.bars}
    assert states == {
        "published": MEASURED,
        "in_sample": NOT_COMPARABLE,
        "out_of_sample": NOT_COMPARABLE,
    }
    assert all(b.value is None for b in d.bars if b.period != "published")


def test_a_statistic_not_stored_is_not_stored_never_zero() -> None:
    b = bars("decile_spread", decile_spread=None)
    assert (b["out_of_sample"].value, b["out_of_sample"].state) == (None, NOT_STORED)
    assert decay_of(published(), 20, None, None)  # an older run has no in-sample row
    older = decay_of(published(), 20, None, row(kind="frozen"))
    assert older is not None and older.bars[1].state == NOT_STORED


def test_a_hidden_out_of_sample_result_is_withheld() -> None:
    d = decay_of(published(), 20, row(kind="in_sample"), row(kind="frozen"), hidden=True)
    assert d is not None
    assert [b.state for b in d.bars] == [MEASURED, MEASURED, OOS_HIDDEN]
    assert d.bars[2].value is None and d.bars[2].n is None


def test_an_edge_that_publishes_nothing_keeps_its_decay_with_the_paper_not_given() -> None:
    d = judge("e", result(), SPLIT, T).decay
    assert d is not None and d.published is None
    assert (d.measure, d.unit) == ("lift_pts", POINTS)
    by = {b.period: b for b in d.bars}
    assert (by["published"].value, by["published"].state) == (None, NOT_GIVEN)
    assert by["out_of_sample"].state == MEASURED and by["out_of_sample"].value == pytest.approx(
        10.0
    )
    assert decay_of(None, 20, None, None).bars[1].state == NOT_STORED


def test_the_published_figure_is_shown_after_the_haircut_of_its_leg_beside_the_oos_bar() -> None:
    """ADR 0065 amendment 2026-10-17: display only, the verdict never reads it."""
    rows = result(oos={"decile_sessions": 11, "decile_spread": 0.0050})
    paper = replace(published("decile_spread", value=0.0200), leg="long_short")  # a half off
    v = judge("e", rows, SPLIT, T, facts=EdgeFacts(paper))
    assert v.decay is not None and v.decay.expected is not None
    e = v.decay.expected
    assert (e.leg, e.haircut, e.value) == ("long_short", 0.5, pytest.approx(0.0100))
    assert (e.realised, e.share) == (0.0050, pytest.approx(0.5))
    assert e.summary == (
        "Published 2.00%, expect 1.00% (50% off for a long-short figure). "
        "Out of sample it is 0.50%, 50% of that."
    )
    only = replace(paper, leg="long")
    long_side = judge("e", rows, SPLIT, T, facts=EdgeFacts(only)).decay
    assert long_side is not None and long_side.expected is not None
    assert long_side.expected.value == pytest.approx(0.0200 * (1 - 0.333))
    assert "33% off for a long figure" in long_side.expected.summary
    same = judge("e", rows, SPLIT, T, facts=EdgeFacts(only)).verdict
    assert same == v.verdict  # the leg moves no verdict


def test_there_is_no_expected_figure_without_a_published_one_or_an_out_of_sample_value() -> None:
    rows = result(oos={"decile_sessions": 11, "decile_spread": 0.02})
    assert judge("e", rows, SPLIT, T).decay.expected is None  # type: ignore[union-attr]
    other = replace(published(), horizon_sessions=60)  # not the verdict's holding period
    d = judge("e", rows, SPLIT, T, facts=EdgeFacts(other)).decay
    assert d is not None and d.expected is not None
    assert (d.expected.realised, d.expected.share) == (None, None)
    assert d.expected.summary == "Published 1.31%, expect 0.87% (33% off for a long figure)."
