"""``slice_measures``: per-slice numbers pooled from per-session stats, by hand. Counts are
explicit; a statistic that is undefined is None (one session has no sd), never a made-up zero."""

from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np
import pytest

from algotrade.quant.edges.statistics import break_even_cost, deflated_sharpe, moments, sharpe
from algotrade.services.evaluation.cross_section.measures import (
    CostGrid,
    Pick,
    SessionStat,
    Slice,
    SliceMeasure,
    cost_measures,
    decile_means,
    deflate,
    edge_slices,
    pool_stats,
    slice_measures,
    trial_value,
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
    assert decile_means([0.1] * 9) == ()
    means = decile_means([float(v) for v in range(20, 0, -1)])  # 20 names, 2 per decile
    assert means == pytest.approx([19.5 - 2 * i for i in range(10)])
    assert means[0] == pytest.approx(19.5) and means[0] - means[-1] == pytest.approx(19.5 - 1.5)


def test_slice_decile_means_average_the_sessions_that_had_deciles_and_are_empty_otherwise() -> None:
    first = stat(date(2026, 1, 5), (0.01,), (0.0,), 1, deciles=tuple(float(i) for i in range(10)))
    second = stat(
        date(2026, 1, 6), (0.01,), (0.0,), 1, deciles=tuple(float(i) for i in range(10, 20))
    )
    bare = stat(date(2026, 1, 7), (0.01,), (0.0,), 1)  # too few scored names: no deciles
    (m,) = slice_measures([first, second, bare], [ALL])
    assert m.decile_means == pytest.approx([5.0 + i for i in range(10)])
    (none,) = slice_measures([bare], [ALL])
    assert none.decile_means == ()  # not measured: never ten zeros


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


def _stats() -> list[SessionStat]:
    days = [date(2025, 12, 30), date(2026, 3, 31), date(2026, 4, 1), date(2026, 4, 30)]
    return [stat(d, (0.01,), (0.0, 0.01), 1) for d in days]


def _year_parts(split: date | None) -> dict[str, list[date]]:
    stats = _stats()
    return {
        s.value: [x.session for x in stats if s.keep(x)]
        for s in edge_slices(stats, split, exploratory=False)
        if s.kind == "year_part"
    }


def test_a_split_inside_a_year_cuts_it_into_two_year_part_slices() -> None:
    parts = _year_parts(date(2026, 4, 1))
    assert list(parts) == ["2026:in_sample", "2026:out_of_sample"]
    assert parts["2026:in_sample"] == [date(2026, 3, 31)]
    assert parts["2026:out_of_sample"] == [date(2026, 4, 1), date(2026, 4, 30)]
    year = next(s for s in edge_slices(_stats(), date(2026, 4, 1), False) if s.value == "2026")
    assert sum(len(v) for v in parts.values()) == sum(year.keep(x) for x in _stats())


def test_a_split_on_a_year_start_or_none_makes_no_year_part() -> None:
    assert _year_parts(date(2026, 1, 1)) == {}
    assert _year_parts(None) == {}


def test_a_split_cuts_each_regime_label_into_two_regime_part_slices() -> None:
    stats = [
        stat(date(2026, 3, 30), (0.01,), (0.0,), 1, regime="CALM"),
        stat(date(2026, 3, 31), (0.01,), (0.0,), 1, regime="STRESS"),
        stat(date(2026, 4, 1), (0.01,), (0.0,), 1, regime="CALM"),
        stat(date(2026, 4, 2), (0.01,), (0.0,), 1, regime="CALM"),
    ]
    split = date(2026, 4, 1)
    parts = {
        s.value: [x.session.day for x in stats if s.keep(x)]
        for s in edge_slices(stats, split, exploratory=False)
        if s.kind == "regime_part"
    }
    assert parts == {
        "CALM:in_sample": [30],
        "CALM:out_of_sample": [1, 2],
        "STRESS:in_sample": [31],
        "STRESS:out_of_sample": [],
    }
    whole = [s for s in edge_slices(stats, split, False) if s.kind == "regime"]
    assert [s.value for s in whole] == ["CALM", "STRESS"]  # the whole-run rows stay
    assert not [s for s in edge_slices(stats, None, False) if s.kind == "regime_part"]


def test_a_block_pools_its_days_picks_in_order_and_sums_hits_per_cost_level() -> None:
    """Leg v2 (ADR 0064): an event block keeps every day's picks, the first day's first, and adds
    the hits at each cost level; a day without levels (not a return) leaves the block without."""
    a, b = Pick("EQ:A", 1, "", 0.1, True), Pick("EQ:B", 1, "no_entry_bar")
    day1 = SessionStat(date(2026, 9, 1), "CALM", (0.1,), 1, picks=(a,), base_hits_at=(4, 3),
                       pick_hits_at=(1, 1))  # fmt: skip
    day2 = SessionStat(date(2026, 9, 2), "CALM", (), 0, picks=(b,), base_hits_at=(2, 1),
                       pick_hits_at=(0, 0))  # fmt: skip
    pooled = pool_stats([day1, day2])
    assert pooled.picks == (a, b)
    assert (pooled.base_hits_at, pooled.pick_hits_at) == ((6, 4), (1, 1))
    bare = SessionStat(date(2026, 9, 3), "CALM")
    assert pool_stats([day1, bare]).base_hits_at == ()


# --- cost rows and capacity columns (ADR 0064 decision 5) ---

DOC_BP = 20.0  # the document's own cost: the stored values are net of it
GRID = (0.0, 15.0, 50.0)


def costed(day: date, adv: tuple[float | None, ...] = (), **kw: object) -> SessionStat:
    """Two counted picks (gross +4% and -1%, net of 20 bp) among six names; per grid level (0, 15
    and 50 bp) the names that hit, from hand: only the +4% pick of the picks, 3, 2, 1 of all."""
    found = tuple(Pick(f"P{i}", i, adv=a) for i, a in enumerate(adv, start=1))
    return SessionStat(
        session=day, regime="BULL", pick_values=(0.0380, -0.0120), pick_hits=1,
        rest=moments((0.0, 0.01, -0.02, 0.0)), base_hits=2, base_hits_at=(3, 2, 1),
        pick_hits_at=(1, 1, 1), picks=found, **kw,
    )  # type: ignore[arg-type]  # fmt: skip


def cost_rows(stats: list[SessionStat], bp: float | None = DOC_BP, **kw: object):  # type: ignore[no-untyped-def]
    sl = [Slice("all", "all", lambda _: True), Slice("year", "2026", lambda _: True)]
    found = slice_measures(stats, sl, **kw)
    if bp is not None:
        found += cost_measures(stats, sl, found, CostGrid(bp, GRID))
    return {(m.slice_kind, m.slice_value): m for m in found}


def test_cost_rows_are_the_document_cost_plus_the_grid_for_the_periods_only() -> None:
    rows = cost_rows([costed(date(2026, 1, 5)), costed(date(2026, 1, 6))])
    assert sorted(v for (k, v) in rows if k == "cost") == ["all:0", "all:15", "all:20", "all:50"]
    assert ("cost", "2026:20") not in rows  # a year is not a cost period


def test_a_cost_row_nets_the_gross_mean_at_its_own_cost_and_counts_its_own_hits() -> None:
    rows = cost_rows([costed(date(2026, 1, 5)), costed(date(2026, 1, 6))])
    gross = (0.0380 - 0.0120) / 2 + DOC_BP / 1e4  # the stored mean is net of the 20 bp
    for bp in (0, 15, 20, 50):
        m = rows["cost", f"all:{bp}"]
        assert m.mean_excess_picks == pytest.approx(gross - bp / 1e4)
        assert (m.sessions, m.picks, m.eligible) == (2, 4, 12)
    zero, doc, fifty = rows["cost", "all:0"], rows["cost", "all:20"], rows["cost", "all:50"]
    assert (zero.hits, zero.base_hits, zero.hit_rate, zero.base_rate) == (2, 6, 0.5, 0.5)
    assert (doc.hits, doc.base_hits) == (rows["all", "all"].hits, rows["all", "all"].base_hits)
    assert (fifty.hits, fifty.base_hits) == (2, 2)
    assert fifty.lift == pytest.approx(0.5 / (2 / 12))
    assert fifty.bh_mean == pytest.approx(rows["all", "all"].bh_mean + 0.0020 - 0.0050)


def test_the_decile_spread_is_cost_invariant_so_a_cost_row_does_not_restate_it() -> None:
    rows = cost_rows([costed(date(2026, 1, 5), spread=0.1, deciles=(0.1, 0.0))])
    assert rows["all", "all"].decile_spread == pytest.approx(0.1)
    for (kind, _), m in rows.items():
        if kind == "cost":
            assert m.decile_spread is None and m.decile_t is None and m.decile_means == ()


def test_break_even_is_the_gross_mean_in_basis_points_whatever_row_it_is_read_from() -> None:
    rows = cost_rows([costed(date(2026, 1, 5))])
    gross_bp = ((0.0380 - 0.0120) / 2 + DOC_BP / 1e4) * 1e4
    for bp in (0, 15, 20, 50):
        row = rows["cost", f"all:{bp}"]
        assert break_even_cost(row.mean_excess_picks, bp) == pytest.approx(gross_bp)
    assert break_even_cost(None, 15) is None


def test_no_costs_no_cost_rows_and_a_level_a_leg_did_not_count_is_skipped() -> None:
    assert not [k for k in cost_rows([costed(date(2026, 1, 5))], bp=None) if k[0] == "cost"]
    old = stat(date(2026, 1, 5), (0.01,), (), 1)  # a leg with no hits per level
    rows = cost_rows([costed(date(2026, 1, 6)), old])
    assert sorted(v for (k, v) in rows if k == "cost") == ["all:20"]  # only the stored net one


def test_a_period_with_no_picks_has_cost_rows_with_nothing_measured() -> None:
    empty = SessionStat(session=date(2026, 1, 5), regime="BULL", base_hits_at=(0, 0, 0),
                        pick_hits_at=(0, 0, 0))  # fmt: skip
    rows = cost_rows([empty])
    m = rows["cost", "all:15"]
    assert m.mean_excess_picks is None and m.hit_rate is None and m.lift is None


def test_capacity_is_the_median_known_and_below_floor_count_of_the_picks_adv() -> None:
    day = costed(date(2026, 1, 5), adv=(10e6, None, 2e6, 4e6))
    (m,) = slice_measures([day], [ALL], adv_floor=5e6)
    assert m.pick_adv_median == pytest.approx(4e6)  # of the three known: 2, 4, 10 million
    assert (m.pick_adv_known, m.pick_adv_low) == (3, 2)
    none_known = costed(date(2026, 1, 6), adv=(None, None))
    (n,) = slice_measures([none_known], [ALL], adv_floor=5e6)
    assert n.pick_adv_median is None and (n.pick_adv_known, n.pick_adv_low) == (0, 0)


def test_capacity_counts_only_the_counted_picks() -> None:
    kept = Pick("A", 1, adv=1e6)
    out = Pick("B", 2, reason="no_entry_bar", adv=9e6)
    s = SessionStat(session=date(2026, 1, 5), regime="BULL", pick_values=(0.01,), picks=(kept, out))
    (m,) = slice_measures([s], [ALL], adv_floor=5e6)
    assert (m.pick_adv_known, m.pick_adv_low, m.pick_adv_median) == (1, 1, 1e6)


def test_pooling_event_days_keeps_the_hits_per_level_and_the_picks() -> None:
    a, b = costed(date(2026, 1, 5), adv=(1e6,)), costed(date(2026, 1, 6), adv=(2e6,))
    block = pool_stats([a, b])
    assert block.pick_hits_at == (2, 2, 2) and len(block.picks) == 2


def test_a_below_outcomes_oriented_mean_moves_the_other_way_with_cost() -> None:
    """Stored values are ``sign * (gross - cost)``: at a higher cost a ``below`` mean rises, and
    the break-even read from any level is the same gross in basis points."""
    day = costed(date(2026, 1, 5))
    sl = [Slice("all", "all", lambda _: True)]
    base = slice_measures([day], sl)
    rows = {m.slice_value: m for m in cost_measures([day], sl, base, CostGrid(DOC_BP, GRID, -1.0))}
    own = rows["all:20"].mean_excess_picks
    assert own is not None
    assert rows["all:50"].mean_excess_picks == pytest.approx(own + 30 / 1e4)  # sign * (20 - 50)
    assert rows["all:0"].mean_excess_picks == pytest.approx(own - 20 / 1e4)
    for bp in (0, 20, 50):
        got = break_even_cost(rows[f"all:{bp}"].mean_excess_picks, bp, -1.0)
        assert got == pytest.approx(break_even_cost(own, DOC_BP, -1.0))


# Trial statistics of an outcome that is not a return (ADR 0064 amendment 2026-10-11)


def wins_stat(day: date, cushions: tuple[float, ...], hits: int, base_hits: int) -> SessionStat:
    """A cushion session: the picks' cushions, ``hits`` of them won; 10 eligible names."""
    rest = tuple(0.5 for _ in range(10 - len(cushions)))
    return stat(day, cushions, rest, hits, base_hits=base_hits)


DAYS = [date(2026, 1, 5) + timedelta(days=7 * i) for i in range(40)]


def _cushions(shift: int = 0) -> list[SessionStat]:
    """Big, steady cushions (a cushion Sharpe near 10) whose wins only sometimes beat the base."""
    return [
        wins_stat(d, (2.0 + 0.01 * ((i + shift) % 3), 2.1), 1 + (i + shift) % 2, 6)
        for i, d in enumerate(DAYS)
    ]


def test_a_win_rate_outcomes_sharpe_is_of_the_excess_wins_never_the_cushion() -> None:
    stats = _cushions()
    (m,) = slice_measures(stats, [ALL], wins=True)
    excess = [s.pick_hits / len(s.pick_values) - s.base_hits / s.eligible for s in stats]
    assert m.sharpe == pytest.approx(sharpe(excess))
    assert m.sharpe < 1  # the cushion's would be about 10: a cushion is not P&L
    (returns,) = slice_measures(stats, [ALL])  # a return outcome keeps the picks' mean
    assert returns.sharpe == pytest.approx(sharpe([s.pick_mean for s in stats]))


def test_a_session_with_no_counted_pick_has_no_excess_wins() -> None:
    empty = stat(date(2026, 1, 5), (), (0.1, 0.2), 0, base_hits=1)
    assert empty.excess_wins is None and trial_value(empty, True) is None
    one = wins_stat(date(2026, 1, 5), (1.0, 2.0), 1, 4)
    assert trial_value(one, True) == pytest.approx(0.5 - 0.4)
    assert trial_value(one, False) == pytest.approx(1.5)


@dataclass(frozen=True)
class Trial:
    """The ``Scored`` side of a harness result."""

    name: str
    role: str
    unit: str | None
    stats: tuple[SessionStat, ...]
    measures: tuple[SliceMeasure, ...]
    horizon: int = 15

    @property
    def wins(self) -> bool:
        return self.unit in ("cushion", "ratio")


def trial(
    name: str, stats: list[SessionStat], role: str = "screener", unit: str = "cushion"
) -> Trial:
    wins = unit in ("cushion", "ratio")
    return Trial(name, role, unit, tuple(stats), tuple(slice_measures(stats, [ALL], wins=wins)))


def _ratio_stats() -> list[SessionStat]:
    """A ratio outcome whose oriented values are large and negative (a Sharpe of about -6)."""
    return [
        stat(d, (-3.0 - 0.5 * (i % 2),), (-3.0,) * 9, i % 2, base_hits=5)
        for i, d in enumerate(DAYS)
    ]


def _by_name(results: list[Trial]) -> dict[str, SliceMeasure]:
    return {r.name: r.measures[0] for r in results}


def test_the_dsr_peers_are_the_screeners_of_the_horizon_and_unit_only() -> None:
    """An extreme baseline, a screener of another unit or of another horizon does not move a
    screener's deflated Sharpe or PBO: they are not trials of the same hypothesis."""
    own = [trial("a", _cushions()), trial("b", _cushions(1))]
    alone = _by_name(deflate(own, 126))
    extreme = [
        trial("decoy", [wins_stat(d, (9.0, 9.0), 2, 0) for d in DAYS], role="baseline"),
        trial("ratio", _ratio_stats(), unit="ratio"),
        replace_horizon(trial("long", [wins_stat(d, (5.0, 5.0), 2, 1) for d in DAYS]), 30),
    ]
    mixed = _by_name(deflate([*own, *extreme], 126))
    for name in ("a", "b"):
        assert mixed[name].deflated_sharpe == pytest.approx(alone[name].deflated_sharpe)
        assert mixed[name].pbo == alone[name].pbo
        assert mixed[name].trials == 126


def test_a_win_rate_trial_is_deflated_on_its_excess_wins() -> None:
    a, b = _cushions(), _cushions(1)
    got = _by_name(deflate([trial("a", a), trial("b", b)], 126))
    excess = [s.excess_wins for s in a]
    peers = [sharpe([s.excess_wins for s in x]) for x in (a, b)]
    want = deflated_sharpe(excess, 126, float(np.var(peers, ddof=1)))
    assert got["a"].deflated_sharpe == pytest.approx(want)
    cushion = deflated_sharpe([s.pick_mean for s in a], 126, float(np.var(peers, ddof=1)))
    assert got["a"].deflated_sharpe != pytest.approx(cushion)  # never the cushion's series


def test_a_baseline_is_deflated_against_the_screeners_and_a_lone_screener_has_no_pbo() -> None:
    base = trial("decoy", _cushions(2), role="baseline")
    one = _by_name(deflate([trial("a", _cushions()), base], 10))
    assert one["a"].pbo is None and one["decoy"].pbo is None  # one trial: nothing to compare
    want = deflated_sharpe([s.excess_wins for s in _cushions(2)], 10, 1 / (len(DAYS) - 1))
    assert one["decoy"].deflated_sharpe == pytest.approx(want)


def test_a_lone_trial_is_deflated_by_the_trial_count_against_the_nulls_sharpe_variance() -> None:
    """Fewer than two peers: V = 1 / (T - 1), so SR0 > 0 and 126 trials still deflate (with
    V = 0 the deflated Sharpe would be the undeflated probabilistic Sharpe ratio)."""
    values = [s.excess_wins for s in _cushions()]
    (got,) = deflate([trial("a", _cushions())], 126)
    want = deflated_sharpe(values, 126, 1 / (len(values) - 1))
    assert got.measures[0].deflated_sharpe == pytest.approx(want)
    undeflated = deflated_sharpe(values, 126, 0.0)
    assert want is not None and undeflated is not None and want < undeflated
    assert got.measures[0].pbo is None  # a lone trial has no PBO, never one against a baseline


def replace_horizon(t: Trial, horizon: int) -> Trial:
    return Trial(t.name, t.role, t.unit, t.stats, t.measures, horizon)


def _spread_day(day: date, longs: tuple[float, ...], shorts: tuple[float, ...]) -> SessionStat:
    return stat(day, longs, (0.0, 0.01), 1, base_hits=3, short_values=shorts, spread=0.1)


def test_a_long_short_session_is_worth_its_spread_and_never_half_of_one() -> None:
    both = _spread_day(date(2026, 1, 5), (0.02, 0.04), (0.01, 0.03))
    assert both.spread_value == pytest.approx(0.03 + 0.02) and both.pick_mean == both.spread_value
    assert trial_value(both, wins=True) == pytest.approx(0.05)  # not the excess wins
    assert _spread_day(date(2026, 1, 6), (0.02,), ()).spread_value is None  # no short leg counted
    assert _spread_day(date(2026, 1, 6), (), (0.02,)).spread_value is None
    plain = stat(date(2026, 1, 7), (0.02, 0.04), (0.0,), 1)
    assert plain.short_values is None and plain.pick_mean == pytest.approx(0.03)


def test_a_long_short_measure_has_no_hit_rate_base_rate_or_lift_never_zero() -> None:
    days = [
        _spread_day(date(2026, 1, 5 + i), (0.02, 0.04), (0.01 + i / 100, 0.03 + i / 100))
        for i in range(3)
    ]
    (m,) = slice_measures(days, [ALL])
    assert (m.hit_rate, m.base_rate, m.lift, m.effect_size, m.bh_mean) == (None,) * 5
    assert m.mean_excess_picks == pytest.approx(0.06)  # 0.03 + (0.02, 0.03, 0.04)
    assert m.sharpe == pytest.approx(sharpe([0.05, 0.06, 0.07]))  # of the spreads
    assert (m.sessions, m.picks, m.decile_spread) == (3, 6, pytest.approx(0.1))
    mixed = [*days, stat(date(2026, 1, 9), (0.02,), (0.0,), 1, short_values=(), spread=0.1)]
    (n,) = slice_measures(mixed, [ALL])
    assert n.mean_excess_picks == pytest.approx(0.06)  # a session with no short leg is no spread


def test_a_pooled_event_block_keeps_its_days_short_legs_only_when_some_day_has_one() -> None:
    one = _spread_day(date(2026, 1, 5), (0.02,), (0.01,))
    two = _spread_day(date(2026, 1, 6), (0.04,), (0.03,))
    assert pool_stats([one, two]).short_values == (0.01, 0.03)
    plain = stat(date(2026, 1, 5), (0.02,), (0.0,), 1)
    assert pool_stats([plain, plain]).short_values is None
