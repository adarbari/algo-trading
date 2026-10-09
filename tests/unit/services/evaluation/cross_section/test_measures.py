"""``slice_measures``: per-slice numbers pooled from per-session stats, by hand. Counts are
explicit; a statistic that is undefined is None (one session has no sd), never a made-up zero."""

from datetime import date

import numpy as np
import pytest

from algotrade.quant.edge_statistics import moments
from algotrade.services.evaluation.cross_section.measures import (
    SessionStat,
    Slice,
    decile_means,
    slice_measures,
)

ALL = Slice("all", "all", lambda _: True)


def stat(
    day: date, picks: tuple[float, ...], rest: tuple[float, ...], hits: int, **kw: object
) -> SessionStat:
    return SessionStat(
        session=day, regime=str(kw.pop("regime", "BULL")), pick_values=picks, pick_hits=hits,
        rest=moments(rest), base_hits=int(kw.pop("base_hits", hits)), **kw,
    )  # type: ignore[arg-type]  # fmt: skip


A = stat(
    date(2025, 12, 31),
    (0.04, -0.01),
    (0.0, 0.02, -0.02, 0.0),
    1,
    base_hits=2,
    spread=0.10,
    top_decile=0.05,
)
B = stat(
    date(2026, 1, 30),
    (0.02,),
    (-0.02, 0.01, 0.03),
    1,
    base_hits=2,
    spread=0.20,
    top_decile=0.07,
    regime="BEAR",
)


def test_pooled_rates_lift_means_and_independent_sessions() -> None:
    (m,) = slice_measures([A, B], [ALL])
    assert (m.sessions, m.picks, m.hits, m.eligible, m.base_hits) == (2, 3, 2, 10, 4)
    assert m.hit_rate == pytest.approx(2 / 3)
    assert m.base_rate == pytest.approx(0.4)
    assert m.lift == pytest.approx((2 / 3) / 0.4)
    assert m.mean_excess_picks == pytest.approx((0.04 - 0.01 + 0.02) / 3)
    assert m.bh_mean == pytest.approx((0.05 + 0.0 + 0.02 - 0.02 + 0.0 - 0.02 + 0.01 + 0.03) / 10)
    assert m.top_decile_mean == pytest.approx(0.06)
    assert m.decile_spread == pytest.approx(0.15)
    assert m.decile_sessions == 2
    assert m.decile_t == pytest.approx(0.15 / (0.0707106781 / 2**0.5), rel=1e-6)


def test_slices_keep_their_own_sessions() -> None:
    year = Slice("year", "2026", lambda s: s.session.year == 2026)
    bear = Slice("regime", "BEAR", lambda s: s.regime == "BEAR")
    _, y, r = slice_measures([A, B], [ALL, year, bear])
    assert (y.sessions, y.picks) == (1, 1) and (r.sessions, r.picks) == (1, 1)
    assert y.sharpe is None and y.decile_t is None  # one session has no sd
    assert y.decile_spread == pytest.approx(0.20)


def test_an_empty_slice_is_none_not_zero() -> None:
    (m,) = slice_measures([A], [Slice("frozen", "frozen", lambda s: s.session.year > 2030)])
    assert (m.sessions, m.picks, m.eligible) == (0, 0, 0)
    assert m.hit_rate is None and m.base_rate is None and m.lift is None
    assert m.bh_mean is None and m.decile_spread is None and m.effect_size is None


def test_counts_of_excluded_and_delisted_picks_and_survivorship_sessions_add_up() -> None:
    a = stat(
        date(2026, 1, 2),
        (0.1,),
        (),
        1,
        excluded_unclosed=2,
        excluded_missing=1,
        delisted=1,
        pre_snapshot=True,
    )
    b = stat(date(2026, 2, 2), (0.1,), (), 1, excluded_unclosed=1)
    (m,) = slice_measures([a, b], [ALL])
    assert (m.excluded_unclosed, m.excluded_missing, m.delisted, m.pre_snapshot_sessions) == (
        3,
        1,
        1,
        1,
    )


def test_deciles_need_ten_names_and_split_best_first() -> None:
    assert decile_means([0.1] * 9) is None
    top, spread = decile_means([float(v) for v in range(20, 0, -1)])  # 20 names, 2 per decile
    assert top == pytest.approx(19.5) and spread == pytest.approx(19.5 - 1.5)


def test_a_model_screener_slice_is_in_sample_when_it_keeps_a_session_before_frozen_from() -> None:
    first, second = A.session, B.session
    assert first < second
    slices = [
        Slice("all", "all", lambda _: True),
        Slice("frozen", "frozen", lambda s: s.session >= second),
        Slice("year", "y", lambda s: s.session == first),
    ]
    flags = lambda **kw: [m.in_sample for m in slice_measures([A, B], slices, **kw)]  # noqa: E731
    assert flags(model=True, frozen_from=second) == [True, False, True]
    assert flags(model=True, frozen_from=first) == [False, False, False]  # nothing before it
    assert flags(model=True) == [True, True, True]  # no frozen period: all fitted-on unknown
    assert flags(model=False, frozen_from=second) == [False, False, False]  # a rule screener


def test_pooled_running_moments_equal_the_raw_pooled_values() -> None:
    """bh_mean and effect_size from per-session moments match the formulas over every value."""
    rows = [A, B]
    (m,) = slice_measures(rows, [ALL])
    picks = np.array([v for r in rows for v in r.pick_values])
    rest = np.array([0.0, 0.02, -0.02, 0.0, -0.02, 0.01, 0.03])
    assert m.bh_mean == pytest.approx(np.concatenate([picks, rest]).mean(), rel=1e-12)
    nx, ny = picks.size, rest.size
    pooled = ((nx - 1) * picks.var(ddof=1) + (ny - 1) * rest.var(ddof=1)) / (nx + ny - 2)
    g = (picks.mean() - rest.mean()) / np.sqrt(pooled) * (1 - 3 / (4 * (nx + ny) - 9))
    assert m.effect_size == pytest.approx(g, rel=1e-9)
