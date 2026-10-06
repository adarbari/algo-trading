"""Bull and bear dating: synthetic level paths with known turns, each rule, drawdowns, errors;
and the paper's monthly rules on the recorded S&P 500 monthly series (Shiller, 1970-2013)."""

from collections.abc import Callable
from pathlib import Path

import numpy as np
import numpy.typing as npt
import pandas as pd
import pytest

from algotrade.quant import turning_points as tp
from algotrade.quant.turning_points import Phase


def path(start: float, *legs: tuple[float, int]) -> npt.NDArray[np.float64]:
    """Geometric legs: each ``(target, n)`` moves to ``target`` over ``n`` observations."""
    out = [start]
    for target, n in legs:
        first = out[-1]
        out += list(first * (target / first) ** (np.arange(1, n + 1) / n))
    return np.array(out)


# Two 25% falls: peaks at 20 and 54, troughs at 30 and 66, then a rise to the end.
TWO_FALLS = path(100, (150, 20), (112.5, 10), (180, 24), (135, 12), (200, 20))


def kinds(phases: list[Phase]) -> list[tuple[int, int, str]]:
    return [(p.start, p.end, p.kind) for p in phases]


def test_pagan_sossounov_dates_two_25pct_falls() -> None:
    phases = tp.pagan_sossounov(TWO_FALLS)
    assert kinds(phases) == [(20, 30, "bear"), (30, 54, "bull"), (54, 66, "bear")]
    assert [p.change for p in phases] == pytest.approx([-0.25, 0.6, -0.25], rel=1e-12)


def test_lunde_timmermann_dates_two_25pct_falls() -> None:
    phases = tp.lunde_timmermann(TWO_FALLS)
    # The trough at the start is not a turn (censored); the last rise stays open.
    assert kinds(phases) == [(20, 30, "bear"), (30, 54, "bull"), (54, 66, "bear")]
    assert phases[0].change == pytest.approx(-0.25, rel=1e-12)


def test_lunde_timmermann_thresholds() -> None:
    # A 15% fall is not a bear at 20% but is at 10%.
    levels = path(100, (130, 10), (110.5, 5), (160, 10), (100, 10))
    assert kinds(tp.lunde_timmermann(levels)) == []  # only the censored start and one peak
    assert kinds(tp.lunde_timmermann(levels, down=0.10)) == [(10, 15, "bear"), (15, 25, "bull")]


def test_lunde_timmermann_starting_with_a_fall() -> None:
    # A flat start: the running high never moves off index 0, which is censored.
    levels = np.concatenate([[100.0, 100.0], path(100, (70, 5), (90, 5), (60, 5))])
    assert kinds(tp.lunde_timmermann(levels)) == [(7, 12, "bull")]


def test_short_small_phases_are_removed() -> None:
    # A 10% dip over 3 observations, recovered in 3: both phases are under 4 and under 20%.
    levels = path(100, (130, 20), (117, 3), (140, 3), (180, 20))
    assert tp.pagan_sossounov(levels, window=2) == []


def test_a_large_move_may_break_the_minimum_phase() -> None:
    levels = path(100, (130, 20), (85, 2), (140, 20), (180, 20))
    phases = tp.pagan_sossounov(levels, window=2)
    assert kinds(phases) == [(20, 22, "bear")]
    assert phases[0].change == pytest.approx(85 / 130 - 1, rel=1e-12)


def test_short_cycles_are_removed_keeping_the_higher_peak() -> None:
    # Peaks at 20 (130) and 30 (140) are 10 apart: the trough between and the lower peak go.
    levels = path(100, (130, 20), (100, 5), (140, 5), (100, 5), (180, 20))
    assert kinds(tp.pagan_sossounov(levels, window=2)) == [(30, 35, "bear")]


def test_short_cycle_keeps_the_most_extreme_turns() -> None:
    # P 200@20, T 160@40, P 170@50, T 140@57, P 190@62: the cycle 50 -> 62 is short; the
    # lower peak (170@50) goes with the higher of its troughs (160@40), so the bear runs to
    # the 140 low (-30%), not to 160.
    levels = path(100, (200, 20), (160, 20), (170, 10), (140, 7), (190, 5), (150, 10))
    phases = tp.pagan_sossounov(levels, window=3)
    assert kinds(phases) == [(20, 57, "bear"), (57, 62, "bull")]
    assert phases[0].change == pytest.approx(-0.30, rel=1e-12)


def test_short_inner_phase_merges_its_neighbours() -> None:
    # A 3-observation 8% bounce inside a long fall: the fall is one bear phase.
    levels = path(100, (200, 30), (150, 15), (162, 3), (100, 15), (220, 30), (180, 10))
    assert kinds(tp.pagan_sossounov(levels, window=2, min_cycle=4)) == [
        (30, 63, "bear"),
        (63, 93, "bull"),
    ]


def test_short_phase_at_an_end_drops_the_less_extreme_turn() -> None:
    # A last 4% bounce over 3 observations: its peak (104) is below the peak before (150).
    end = path(100, (150, 20), (100, 10), (104, 3), (101, 3))
    assert kinds(tp.pagan_sossounov(end, window=3, min_cycle=4)) == [(20, 30, "bear")]
    # A first 4% dip from the high: its trough (192) is above the trough after (100).
    start = path(100, (200, 10), (192, 3), (196, 3), (100, 20), (150, 20))
    assert kinds(tp.pagan_sossounov(start, window=3, min_cycle=4)) == [(10, 36, "bear")]


def test_adjacent_peaks_keep_the_higher() -> None:
    # Peaks at 10 (150) and 18 (160) with no dated trough between: one turn, at 18.
    levels = path(100, (150, 10), (148, 1), (147, 1), (160, 6), (100, 10), (130, 10))
    assert kinds(tp.pagan_sossounov(levels, window=3)) == [(18, 28, "bear")]


def test_plateau_peak_is_dated_at_its_first_observation() -> None:
    levels = np.concatenate([path(100, (150, 10)), np.full(5, 150.0), path(150, (100, 10))[1:]])
    levels = np.concatenate([levels, path(100, (160, 10))[1:]])
    assert kinds(tp.pagan_sossounov(levels, window=3, min_cycle=4)) == [
        (10, 25, "bear"),
    ]


def test_first_peak_below_an_earlier_level_is_censored() -> None:
    # Starts at 200; the first dated peak (180) is lower, so its fall is not a phase.
    levels = path(200, (150, 2), (180, 8), (100, 10), (250, 20), (180, 10), (260, 20))
    assert kinds(tp.pagan_sossounov(levels, window=3)) == [(20, 40, "bull"), (40, 50, "bear")]


def test_last_trough_above_a_later_level_is_censored() -> None:
    # The trough at 30 (100) is beaten by 99 at the end, outside its +/- 3 window.
    levels = np.concatenate([path(100, (150, 20), (100, 10)), [101.5, 103.0, 101.0, 99.0]])
    assert kinds(tp.pagan_sossounov(levels, window=3)) == []


def test_flat_series_has_no_phases() -> None:
    assert tp.pagan_sossounov(np.full(40, 100.0)) == []
    assert tp.lunde_timmermann(np.full(40, 100.0)) == []


def test_drawdowns_by_hand() -> None:
    out = tp.drawdowns([100.0, 120.0, 90.0, 130.0, 104.0])
    np.testing.assert_allclose(out, [0.0, 0.0, -0.25, 0.0, -0.2], atol=1e-15)


@pytest.mark.parametrize(
    "call",
    [
        lambda: tp.drawdowns(np.ones((3, 2))),
        lambda: tp.drawdowns([100.0, np.nan, 90.0]),
        lambda: tp.drawdowns([100.0, 0.0]),
        lambda: tp.pagan_sossounov(np.ones(20), window=0),
        lambda: tp.pagan_sossounov(np.ones(20), min_move=-0.1),
        lambda: tp.lunde_timmermann(np.ones(20), up=0.0),
        lambda: tp.lunde_timmermann(np.ones(20), down=1.0),
    ],
)
def test_input_errors(call: Callable[[], object]) -> None:
    with pytest.raises(ValueError):
        call()


SHILLER = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "sp500_monthly_shiller.csv"
# Closing-basis peak and trough months of config/site/regime/episodes.toml.
EPISODE_MONTHS = {
    "1973": ("1973-01", "1974-10"),
    "1980": ("1980-11", "1982-08"),
    "1987": ("1987-08", "1987-12"),
    "2000": ("2000-03", "2002-10"),
    "2007": ("2007-10", "2009-03"),
    "2011": ("2011-04", "2011-10"),
}


def _months_apart(a: str, b: str) -> int:
    ya, ma = map(int, a.split("-"))
    yb, mb = map(int, b.split("-"))
    return abs((ya - yb) * 12 + ma - mb)


def test_pagan_sossounov_monthly_dating_of_the_sp500_1970_2013() -> None:
    """The paper's monthly rules (8, 4, 16 months, 20%) on Shiller's monthly averages.

    Pagan and Sossounov's own table (US data to 1997) is not reproduced here: the expected
    turns are the episodes' closing-basis months, met within one month wherever the monthly
    average tracks the daily close. Where it cannot, the divergence is pinned and explained:
    the 2000 average peaked in August (the daily close in March, on a flat top), and the
    averaged lows of 1974 and 2002-03 came after the daily lows; the brief 1990 fall (3 months,
    -15% on averages) is too short and too small for the rules, as the paper's minimum phase
    intends."""
    frame = pd.read_csv(SHILLER, comment="#")
    months = list(frame["month"])
    bears = [
        (months[p.start], months[p.end], round(p.change, 3))
        for p in tp.pagan_sossounov(frame["sp500"].to_numpy(float))
        if p.kind == "bear"
    ]
    assert bears == [
        ("1971-04", "1971-11", -0.099),
        ("1973-01", "1974-12", -0.434),
        ("1976-09", "1978-03", -0.158),
        ("1978-08", "1980-04", -0.009),
        ("1980-11", "1982-07", -0.194),
        ("1983-10", "1984-07", -0.099),
        ("1987-08", "1987-12", -0.268),
        ("2000-08", "2003-02", -0.437),
        ("2007-10", "2009-03", -0.508),
        ("2011-05", "2011-09", -0.123),
    ]
    dated = {peak[:4]: (peak, trough) for peak, trough, _ in bears}
    within = {"1973": (True, False), "2000": (False, False)}  # (peak, trough) within a month
    for key, (peak, trough) in EPISODE_MONTHS.items():
        got_peak, got_trough = dated[key]
        expect = within.get(key, (True, True))
        near = (_months_apart(got_peak, peak) <= 1, _months_apart(got_trough, trough) <= 1)
        assert near == expect, key
    assert not any(peak.startswith("1990") for peak, _, _ in bears)
