"""Measures of a time-series edge: a known result by hand, the slices cut by decision session,
the overlap correction, the timing Sharpe ratio and the trial statistics."""

import math
from datetime import date

import pytest

from algotrade.core.time.calendar import next_session
from algotrade.quant.edges.statistics import welch_t
from algotrade.services.evaluation.time_series.measures import (
    Obs,
    deflate_trial,
    measure,
    measures,
    pbo_among,
    timing_sharpes,
)
from algotrade.services.evaluation.time_series.periods import Period


def at(day: date, inside: bool) -> Period:
    return Period(day, day, day, inside)


def obs(first: date, values: list[float], inside: bool, step: int = 4) -> list[Obs]:
    out, day = [], first
    for v in values:
        out.append(Obs(at(day, inside), v, "calm"))
        for _ in range(step):
            day = next_session(day)
    return out


IN = obs(date(2025, 1, 2), [0.02, 0.01, 0.03, 0.02], True, step=40)
OUT = obs(date(2025, 1, 10), [-0.01, 0.01, -0.02, 0.0, 0.01, -0.01], False, step=20)


def test_a_known_result_by_hand() -> None:
    m = measure("all", "all", [*IN, *OUT], 4)
    assert (m.sessions, m.picks, m.hits, m.eligible, m.base_hits) == (4, 4, 4, 6, 2)
    assert (m.hit_rate, m.base_rate, m.lift) == (1.0, pytest.approx(2 / 6), pytest.approx(3.0))
    assert m.mean_excess_picks == pytest.approx(0.02)
    assert m.bh_mean == pytest.approx(-0.02 / 6)
    diff, t = welch_t([o.value for o in IN], [o.value for o in OUT])
    assert m.decile_spread == pytest.approx(diff) and m.decile_t == pytest.approx(t)
    assert m.decile_sessions == 4 and m.picks_t is not None and m.sharpe is not None
    assert m.deflated_sharpe is None and m.trials is None  # the run's, not a slice's


def test_a_slice_with_no_window_has_no_number_never_a_zero() -> None:
    m = measure("all", "all", OUT, 4)
    assert (m.sessions, m.picks, m.hit_rate, m.decile_spread, m.decile_t) == (
        0,
        0,
        None,
        None,
        None,
    )
    assert m.base_rate == pytest.approx(2 / 6)


def test_slices_are_all_year_regime_and_the_split_sides_by_decision_session() -> None:
    both = [*IN, *OUT]
    split = date(2025, 6, 1)
    rows = measures(both, 4, split, False)
    kinds = [(m.slice_kind, m.slice_value) for m in rows]
    assert kinds[0] == ("all", "all")
    assert ("year", "2025") in kinds and ("regime", "calm") in kinds
    assert kinds[-2:] == [("in_sample", "in_sample"), ("frozen", "frozen")]
    by = {m.slice_kind: m for m in rows}
    before = [o for o in both if o.period.decision < split]
    assert by["in_sample"].picks + by["frozen"].picks == len(IN)
    assert by["in_sample"].eligible == sum(not o.period.inside for o in before)
    assert measures(both, 4, split, True)[-1].slice_kind == "split"
    assert [m.slice_kind for m in measures(both, 4, None, False)] == ["all", "year", "regime"]
    assert [(m.slice_kind, m.sessions) for m in measures([], 4, None, False)] == [("all", 0)]


def test_periods_closer_than_the_window_count_once_in_the_t_ratio() -> None:
    """Periods one session apart with a 4-session window are four overlapping looks at the same
    stretch: they stand for a quarter as many independent ones, and the t shrinks by sqrt(1/4)."""
    spaced = obs(date(2025, 1, 2), [0.02, 0.01, 0.03, 0.02, 0.02, 0.01], True, step=1)
    out = obs(date(2025, 3, 3), [-0.01, 0.01, -0.02, 0.0, 0.01, -0.01], False, step=4)
    m = measure("all", "all", [*spaced, *out], 4)
    flat = measure(
        "all",
        "all",
        [*obs(date(2025, 1, 2), [0.02, 0.01, 0.03, 0.02, 0.02, 0.01], True, step=4), *out],
        4,
    )
    assert m.picks == 6 and m.sessions < 6 and flat.sessions == 6
    assert m.decile_t is not None and flat.decile_t is not None
    assert abs(m.decile_t) < abs(flat.decile_t)
    assert m.picks_t == pytest.approx(
        measure("all", "all", spaced, 4).picks_t, rel=1e-9
    )  # reads the same values over fewer independent sessions


def test_the_timing_sharpe_holds_bills_outside_the_windows() -> None:
    both = sorted([*IN, *OUT], key=lambda o: o.period.first)
    bills = {o.period.decision: 0.001 for o in both}
    got = timing_sharpes(both, bills)
    assert got["periods"] == len(both)
    assert got["timing_sharpe"] is not None and got["buy_hold_sharpe"] is not None
    assert got["timing_sharpe"] > got["buy_hold_sharpe"]  # windows earn, the rest is flat
    assert timing_sharpes(both, {})["periods"] == 0  # no bill known: no period, never a zero rate


def test_deflation_counts_the_trials_and_a_lone_trial_has_no_pbo() -> None:
    m = measure("all", "all", [*IN, *OUT], 4)
    one = deflate_trial(m, [o.value for o in IN], 1, None)
    many = deflate_trial(m, [o.value for o in IN], 50, None)
    assert one.trials == 1 and many.trials == 50 and one.pbo is None
    assert one.deflated_sharpe is not None and many.deflated_sharpe is not None
    assert many.deflated_sharpe < one.deflated_sharpe
    assert deflate_trial(m, [0.01], 1, None).deflated_sharpe is None  # one window: nothing to test


def test_pbo_reads_the_windows_every_instrument_has() -> None:
    days = [date(2025, 1, 2 + i) for i in range(20)]
    a = {d: math.sin(i) * 0.01 for i, d in enumerate(days)}
    b = {d: math.cos(i * 1.7) * 0.01 for i, d in enumerate(days)}
    assert pbo_among({"A": a}) is None  # one instrument: nothing to compare
    assert pbo_among({"A": a, "B": b}) is not None
    assert pbo_among({"A": a, "B": {d: v for d, v in b.items() if d.day % 2}}) is None  # < 16
