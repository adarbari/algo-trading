"""``EdgeDecay``: the paper's figure against the in- and out-of-sample ones of one statistic."""

import pytest

from algotrade.services.read.evaluation.decay import (
    MEASURED,
    NOT_COMPARABLE,
    NOT_STORED,
    OOS_HIDDEN,
    POINTS,
    RETURN,
    decay_of,
)
from algotrade.services.read.evaluation.edges import EdgePublished, EdgeSource
from algotrade.services.read.evaluation.verdict import EdgeFacts, judge
from tests.unit.services.read.evaluation.test_verdict import SPLIT, T, result, row

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


def test_an_edge_that_publishes_nothing_has_no_decay() -> None:
    assert judge("e", result(), SPLIT, T).decay is None
    assert decay_of(None, 20, None, None) is None
