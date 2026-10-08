"""``slice_measures``: per-slice numbers pooled from per-session stats, by hand. Counts are
explicit; a statistic that is undefined is None (one session has no sd), never a made-up zero."""

from datetime import date

import pytest

from algotrade.services.evaluation.cross_section.harness import _slices
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
        rest_values=rest, base_hits=int(kw.pop("base_hits", hits)), **kw,
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


def test_a_model_screeners_slices_are_in_sample_except_the_frozen_one() -> None:
    frozen = date(2026, 4, 1)
    flags = lambda **kw: {  # noqa: E731
        (s.kind, s.value): s.in_sample for s in _slices([A, B], frozen, **kw, frozen_from=frozen)
    }
    model = flags(exploratory=False, model=True)
    assert model[("all", "all")] and model[("frozen", "frozen")] is False
    assert all(v for k, v in model.items() if k[0] in ("year", "regime"))
    assert not any(flags(exploratory=False, model=False).values())  # a rule screener: never
    # An exploratory split before frozen_from holds fitted sessions; one after it does not.
    assert flags(exploratory=True, model=True)[("split", "split")] is False
    early = _slices([A], date(2026, 1, 5), True, True, frozen)
    assert [s.in_sample for s in early if s.kind == "split"] == [True]
    (m,) = slice_measures([A], [Slice("all", "all", lambda _: True, True)])
    assert m.in_sample is True
