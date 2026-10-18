"""Measures of a time-series edge: a known result by hand, the slices cut by decision session,
the overlap correction, the timing Sharpe ratio and the trial statistics."""

import math
from datetime import date

import pytest

from algotrade.core.time.calendar import next_session
from algotrade.quant.edges.statistics import sharpe_t, welch_t
from algotrade.services.evaluation.time_series.measures import (
    Obs,
    deflate_trial,
    measure,
    measures,
    pbo_among,
    timing_sharpes,
    with_pairs,
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


def advance(day: date, n: int) -> date:
    for _ in range(n):
        day = next_session(day)
    return day


def layout(ins: list[float], outs: list[float], h: int = 4) -> list[Obs]:
    """Each window with a stretch tiled right after it, then a gap; spare stretches at the end."""
    out, day = [], date(2025, 1, 2)
    for i, v in enumerate(ins):
        out.append(Obs(at(day, True), v, "calm"))
        day = advance(day, h)
        if i < len(outs):
            out.append(Obs(at(day, False), outs[i], "calm"))
            day = advance(day, 2 * h)
    for v in outs[len(ins) :]:
        out.append(Obs(at(day, False), v, "calm"))
        day = advance(day, 2 * h)
    return with_pairs(out, h)


BOTH = layout([0.02, 0.01, 0.03, 0.02], [-0.01, 0.01, -0.02, 0.0, 0.01, -0.01])
IN = [o for o in BOTH if o.period.inside]
OUT = [o for o in BOTH if not o.period.inside]


def test_a_known_result_by_hand() -> None:
    m = measure("all", "all", BOTH, 4)
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
    both = BOTH
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
    assert m.excluded_missing == 6 and m.picks_t is None  # no stretch beside them: unpaired


def test_the_timing_sharpe_holds_bills_outside_the_windows() -> None:
    both = sorted([*IN, *OUT], key=lambda o: o.period.first)
    bills = {o.period.decision: 0.001 for o in both}
    got = timing_sharpes(both, bills)
    assert got["periods"] == len(both)
    assert got["timing_sharpe"] is not None and got["buy_hold_sharpe"] is not None
    assert got["timing_sharpe"] > got["buy_hold_sharpe"]  # windows earn, the rest is flat
    assert timing_sharpes(both, {})["periods"] == 0  # no bill known: no period, never a zero rate


def test_deflation_counts_the_trials_and_a_lone_trial_has_no_pbo() -> None:
    m = measure("all", "all", BOTH, 4)
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


def test_a_drifting_instrument_with_no_timing_edge_fails_the_paired_t() -> None:
    """Every window and every stretch earns +1% with a little noise: the raw in-window Sharpe
    ratio would be huge, the windows' edge over the stretch beside them is nothing."""
    noise = [0.0004, -0.0003, 0.0002, -0.0004, 0.0003, -0.0002, 0.0004, -0.0001] * 4
    ins = [0.01 + n for n in noise]
    outs = [0.01 + n for n in reversed(noise)]
    m = measure("all", "all", layout(ins, outs), 4)
    raw = sharpe_t(ins)
    assert raw is not None and raw > 10  # drift alone would pass any t bar
    assert m.picks_t is not None and abs(m.picks_t) < 2
    assert m.sharpe is not None and abs(m.sharpe) < 0.4


def test_a_falling_instrument_with_a_real_timing_edge_passes_the_paired_t() -> None:
    """The stretches lose 1% and the windows only 0.4%: negative raw returns, a steady edge."""
    noise = [0.0004, -0.0003, 0.0002, -0.0004, 0.0003, -0.0002, 0.0004, -0.0001] * 4
    ins = [-0.004 + n for n in noise]
    outs = [-0.010 + n for n in reversed(noise)]
    m = measure("all", "all", layout(ins, outs), 4)
    assert all(v < 0 for v in ins) and m.hit_rate == 0.0
    assert m.picks_t is not None and m.picks_t > 3
    assert m.sharpe is not None and m.sharpe > 1


def test_windows_with_no_stretch_beside_them_are_counted_unpaired_never_filled() -> None:
    m = measure("all", "all", layout([0.02, 0.01, 0.03], [-0.01]), 4)  # one stretch, 3 windows
    assert (m.picks, m.excluded_missing) == (3, 2)


def test_a_split_year_and_regime_keep_their_in_sample_side() -> None:
    split = date(2025, 2, 1)
    kinds = {(m.slice_kind, m.slice_value) for m in measures(BOTH, 4, split, False)}
    assert {("year_part", "2025:in_sample"), ("year_part", "2025:out_of_sample")} <= kinds
    assert {("regime_part", "calm:in_sample"), ("regime_part", "calm:out_of_sample")} <= kinds
    none = {m.slice_kind for m in measures(BOTH, 4, None, False)}
    assert not {"year_part", "regime_part"} & none
