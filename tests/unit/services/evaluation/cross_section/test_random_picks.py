"""Random-pick draws: deterministic by (leg key, edge variant, holding period, session), the same
whatever order the names arrive in or range the run has, and measured like a screener's picks."""

import dataclasses
from datetime import date, datetime, timedelta
from typing import Any

import numpy as np
import pandas as pd
import pytest

from algotrade.config.user import UserContext
from algotrade.services.evaluation.cross_section import measuring
from algotrade.services.evaluation.cross_section.harness import (
    EdgeEvaluation,
    RandomPicks,
    evaluate_edge,
)
from algotrade.services.evaluation.cross_section.random_picks import (
    DRAW,
    UNKNOWN_SECTOR,
    RandomStat,
    generator,
    pool_random,
    random_measures,
    random_stat,
    sector_mix,
)
from algotrade.services.evaluation.cross_section.reads import session as session_reads
from algotrade.services.evaluation.cross_section.results import edge_eval_frame
from tests.helpers.stored_frames import stamped
from tests.unit.services.evaluation.cross_section.conftest import (
    AS_OF,
    DAYS,
    World,
    build_world,
    edge,
)
from tests.unit.services.evaluation.cross_section.conftest import (
    IDS as WORLD_IDS,
)
from tests.unit.services.evaluation.cross_section.test_harness import event_edge

DAY = date(2026, 9, 1)
USER = UserContext("site")
IDS = [f"EQ:{i:02d}" for i in range(20)]


def counted(order: list[str] | None = None) -> pd.DataFrame:
    frame = pd.DataFrame(
        {"oriented": [(i - 9.5) / 100 for i in range(20)], "hit": [i >= 10 for i in range(20)]},
        index=pd.Index(IDS, name="instrument_id"),
    )
    return frame if order is None else frame.loc[order]


def draw(
    frame: pd.DataFrame, day: date = DAY, horizon: int = 2, variant: str = "main"
) -> RandomStat:
    found = random_stat(day, frame, set(IDS), 5, 50, generator("hash", variant, horizon, day))
    assert found is not None
    return found


def test_the_same_run_draws_the_same_names_whatever_the_order_they_arrive_in() -> None:
    a = draw(counted())
    b = draw(counted(list(reversed(IDS))))
    np.testing.assert_array_equal(a.value_sums, b.value_sums)
    np.testing.assert_array_equal(a.hit_sums, b.hit_sums)


def test_the_seed_is_the_run_the_edge_variant_the_horizon_and_the_session() -> None:
    base = draw(counted())
    np.testing.assert_array_equal(base.value_sums, draw(counted()).value_sums)
    for other in (
        draw(counted(), variant="cheap"),
        draw(counted(), horizon=5),
        draw(counted(), day=date(2026, 9, 2)),
    ):
        assert not np.array_equal(base.value_sums, other.value_sums)
    rerun = random_stat(DAY, counted(), set(IDS), 5, 50, generator("other hash", "main", 2, DAY))
    assert rerun is not None and not np.array_equal(base.value_sums, rerun.value_sums)


def test_draws_are_taken_only_from_the_pickable_names_that_have_a_counted_outcome() -> None:
    only = {"EQ:19", "EQ:18", "EQ:17", "EQ:16", "EQ:15", "EQ:00"}
    stat = random_stat(DAY, counted().drop(index="EQ:15"), only, 5, 20, generator("h", "m", 2, DAY))
    assert stat is not None
    # Five names drawn from the five pickable with an outcome: every draw is those five.
    assert stat.picks == 5
    assert set(np.round(stat.value_sums, 9)) == {
        round(sum((i - 9.5) / 100 for i in (19, 18, 17, 16, 0)), 9)
    }
    assert (stat.eligible, stat.base_hits) == (19, 9)  # the base is every counted name


def test_nothing_to_draw_is_none() -> None:
    assert random_stat(DAY, counted(), set(), 5, 10, generator("h", "m", 2, DAY)) is None


def test_a_draw_is_measured_like_a_screeners_picks() -> None:
    stat = draw(counted())
    m = random_measures([stat, stat])
    assert len(m) == 50 and {x.slice_kind for x in m} == {DRAW}
    assert [x.slice_value for x in m[:3]] == ["0", "1", "2"]
    first = m[0]
    assert (first.sessions, first.picks, first.eligible, first.base_hits) == (2, 10, 40, 20)
    assert first.hits == 2 * stat.hit_sums[0]
    assert first.hit_rate == pytest.approx(first.hits / 10)
    assert first.base_rate == 0.5 and first.lift == pytest.approx(first.hit_rate / 0.5)
    assert first.mean_excess_picks == pytest.approx(2 * stat.value_sums[0] / 10)
    assert first.decile_spread is None and first.top_decile_mean is None
    assert random_measures([]) == ()


def test_an_event_block_is_one_session_with_the_legs_added() -> None:
    one = draw(counted())
    two = draw(counted(), day=date(2026, 9, 2))
    block = pool_random([one, two])
    assert block.session == DAY and block.picks == 10 and block.eligible == 40
    np.testing.assert_allclose(block.value_sums, one.value_sums + two.value_sums)
    assert pool_random([one]) is one


def test_a_sessions_random_draws_do_not_change_with_the_range_or_the_as_of(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ADR 0063: the draws are seeded by the leg key, not the run hash, so moving the start, the
    end or the ``as_of`` leaves the names drawn at a session as they were."""
    drawn: dict[date, list[Any]] = {}
    real = measuring.random_stat

    def record(day: date, *args: Any, **kwargs: Any) -> Any:
        found = real(day, *args, **kwargs)
        if found is not None:
            drawn.setdefault(day, []).append((found.value_sums.tolist(), found.hit_sums.tolist()))
        return found

    monkeypatch.setattr(measuring, "random_stat", record)
    e = edge(frozen_from="2026-09-04")
    w = build_world()
    evaluate_edge(w.reader, w.results, w.configs, USER, e, DAYS[0], DAYS[-1], AS_OF)
    full = {day: draws[0] for day, draws in drawn.items()}
    assert len(full) >= 2
    drawn.clear()
    later = AS_OF + timedelta(days=1)
    w = build_world()
    evaluate_edge(w.reader, w.results, w.configs, USER, e, DAYS[2], DAYS[-1], later)
    assert drawn and set(drawn) <= set(full)
    assert all(draws[0] == full[day] for day, draws in drawn.items())


# ---- the sector-stratified draws (ADR 0053 amendment 2026-10-18)

SECTORS = {i: ("Tech" if n < 12 else "Energy" if n < 18 else None) for n, i in enumerate(IDS)}
# 12 tech names (EQ:00-11), 6 energy (12-17), 2 with no sector (18-19)
PICKS = ["EQ:00", "EQ:01", "EQ:02", "EQ:03", "EQ:12", "EQ:13", "EQ:18"]  # 4 tech, 2 energy, 1 none


def stratified(
    frame: pd.DataFrame | None = None, picks: list[str] | None = None, day: date = DAY
) -> RandomStat:
    found = random_stat(
        day,
        counted() if frame is None else frame,
        set(IDS),
        len(PICKS if picks is None else picks),
        50,
        generator("hash", "main", 2, day),
        sectors=SECTORS,
        pick_ids=PICKS if picks is None else picks,
        sector_rng=generator("hash", "main|sector", 2, day),
    )
    assert found is not None
    return found


def test_the_sector_mix_counts_the_picks_per_sector_and_names_the_unknown_stratum() -> None:
    assert sector_mix(PICKS, SECTORS) == {"Energy": 2, "Tech": 4, UNKNOWN_SECTOR: 1}
    assert sector_mix([], SECTORS) == {}


def test_stratified_draws_hold_the_picks_sector_mix_in_every_draw() -> None:
    """Values encode the sector (tech 1, energy 10, none 100), so a draw's sum says its mix."""
    values = [
        1.0 if SECTORS[i] == "Tech" else 10.0 if SECTORS[i] == "Energy" else 100.0 for i in IDS
    ]
    frame = pd.DataFrame(
        {"oriented": values, "hit": [True] * 20}, index=pd.Index(IDS, name="instrument_id")
    )
    found = stratified(frame)
    assert found.sector is not None and found.sector.picks == 7
    # 4 tech x 1 + 2 energy x 10 + 1 unknown x 100, in every one of the 50 draws
    np.testing.assert_array_equal(found.sector.value_sums, np.full(50, 124.0))
    np.testing.assert_array_equal(found.sector.hit_sums, np.full(50, 7.0))
    assert found.picks == 7 and not np.all(found.value_sums == 124.0)  # the uniform ones differ


def test_a_sector_with_fewer_names_than_picks_gives_all_of_them() -> None:
    picks = ["EQ:12", "EQ:13", "EQ:14", "EQ:15", "EQ:16", "EQ:17", "EQ:12"]  # 7 energy, 6 exist
    found = stratified(picks=picks)
    assert found.sector is not None and found.sector.picks == 6
    assert found.picks == 7  # the uniform draw is untouched


def test_stratified_draws_are_deterministic_and_independent_of_the_name_order() -> None:
    a = stratified()
    b = stratified(counted(list(reversed(IDS))))
    assert a.sector is not None and b.sector is not None
    np.testing.assert_array_equal(a.sector.value_sums, b.sector.value_sums)
    again = stratified()
    assert again.sector is not None
    np.testing.assert_array_equal(a.sector.value_sums, again.sector.value_sums)
    other = stratified(day=date(2026, 9, 2))
    assert other.sector is not None and not np.array_equal(
        a.sector.value_sums, other.sector.value_sums
    )


def test_the_stratified_stream_leaves_the_uniform_draws_as_they_were() -> None:
    """A second generator: the uniform draws of a screener are the same with or without it."""
    plain = draw(counted())
    both = random_stat(
        DAY, counted(), set(IDS), 5, 50, generator("hash", "main", 2, DAY),
        sectors=SECTORS, pick_ids=PICKS[:5], sector_rng=generator("hash", "main|sector", 2, DAY),
    )  # fmt: skip
    assert both is not None
    np.testing.assert_array_equal(both.value_sums, plain.value_sums)


def test_no_sectors_no_stratified_draws_and_pooling_adds_them() -> None:
    assert draw(counted()).sector is None
    a, b = stratified(), stratified(day=date(2026, 9, 2))
    pooled = pool_random([a, b])
    assert pooled.sector is not None and a.sector is not None and b.sector is not None
    np.testing.assert_array_equal(
        pooled.sector.value_sums, a.sector.value_sums + b.sector.value_sums
    )
    assert pooled.sector.picks == a.sector.picks + b.sector.picks
    view = pooled.stratified()
    assert view is not None and (view.picks, view.eligible) == (
        pooled.sector.picks,
        pooled.eligible,
    )
    mixed = pool_random([a, draw(counted())])  # one leg without them: none for the block
    assert mixed.sector is None and mixed.stratified() is None


def test_zero_picks_keep_the_base_and_zero_stratified_draws() -> None:
    found = random_stat(
        DAY, counted(), set(IDS), 0, 5, generator("h", "m", 2, DAY), sectors=SECTORS,
        pick_ids=[], sector_rng=generator("h", "m|s", 2, DAY),
    )  # fmt: skip
    assert found is not None and found.sector is not None and found.sector.picks == 0


# ---- the harness's random-pick sets: drawn out of sample only, stored, stable


def run(w: World, e=None, as_of: datetime = AS_OF) -> EdgeEvaluation:  # type: ignore[no-untyped-def]
    last = DAYS[-1]
    return evaluate_edge(w.reader, w.results, w.configs, USER, e or edge(), DAYS[0], last, as_of)


def uniform(ev: EdgeEvaluation) -> tuple[RandomPicks, ...]:
    """The uniform random-pick sets of an evaluation (the sector-matched ones are ``kind``
    ``random_sector``)."""
    return tuple(r for r in ev.random_picks if r.kind == "random")


def test_random_picks_need_an_out_of_sample_slice_and_are_drawn_only_there() -> None:
    assert run(build_world()).random_picks == ()  # no frozen_from: nothing out of sample
    ev = run(build_world(), edge(frozen_from="2026-09-04"))
    (found,) = uniform(ev)
    assert (found.edge_variant, found.horizon) == ("main", 2)
    assert len(found.draws) == 1000  # DEFAULT_DRAWS
    first = found.draws[0]
    assert (first.slice_kind, first.sessions, first.picks, first.eligible) == ("draw", 2, 10, 40)
    # Names earn (i - 9.5)%: the screener's top five always hit (lift 2.0, the ceiling); a random
    # five is the top five only 1 time in 252 a session, so almost no draw reaches the ceiling.
    lifts = [d.lift for d in found.draws if d.lift is not None]
    assert sum(lift >= 2.0 for lift in lifts) < 0.01 * len(lifts)
    assert sum(lifts) / len(lifts) == pytest.approx(1.0, abs=0.05)


def sectored(world: Any) -> Any:
    """``world`` with a company snapshot: names 00-09 Technology, 10-19 Energy (the screener's
    top names, the dearest, are all Energy)."""
    snap = DAYS[0] - timedelta(days=3)
    rows = [
        {"instrument_id": iid, "symbol": iid[3:], "cik": str(i), "name": iid, "sic": "1311",
         "sector": "Technology" if i < 10 else "Energy", "fetched_on": snap}
        for i, iid in enumerate(WORLD_IDS)
    ]  # fmt: skip
    world.writer.write_table("instruments/company", snap, "c1", stamped(rows, snap, "c1"))
    return world


def test_the_sector_matched_draws_come_from_the_picks_sectors_beside_the_uniform_ones() -> None:
    """The screener's five dearest names are all Energy and every Energy name wins: a draw
    matched to that mix always hits (lift at the ceiling 2.0) where a uniform draw averages 1."""
    ev = run(sectored(build_world()), edge(frozen_from="2026-09-04"))
    (plain,) = uniform(ev)
    (matched,) = [r for r in ev.random_picks if r.kind == "random_sector"]
    assert (matched.edge_variant, matched.horizon, matched.variant, matched.config_hash) == (
        plain.edge_variant, plain.horizon, plain.variant, plain.config_hash,
    )  # fmt: skip
    first = matched.draws[0]
    assert (first.sessions, first.picks, first.eligible) == (2, 10, 40)
    assert {round(d.lift or 0, 6) for d in matched.draws} == {2.0}
    uniform_lifts = [d.lift for d in plain.draws if d.lift is not None]
    assert sum(uniform_lifts) / len(uniform_lifts) == pytest.approx(1.0, abs=0.05)


def test_the_sector_matched_draws_are_stored_under_their_own_variant_name() -> None:
    ev = run(sectored(build_world()), edge(frozen_from="2026-09-04"))
    frame = edge_eval_frame(ev, "r1", AS_OF)
    matched = frame[frame["variant"] == "random_sector:momo"]
    assert len(matched) == 1000 and set(matched["role"]) == {"random"}
    assert set(matched["slice_kind"]) == {"draw"}


def test_the_same_run_draws_the_same_random_picks_and_the_chunking_does_not_matter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    e = edge(frozen_from="2026-09-04")
    once = run(build_world(), e).random_picks
    assert run(build_world(), e).random_picks == once
    monkeypatch.setattr(measuring, "CHUNK_SESSIONS", 1)
    assert run(build_world(), e).random_picks == once
    assert run(build_world(), edge(frozen_from="2026-09-04", top_k=4)).random_picks != once


def test_random_draws_are_stored_with_the_decile_means_and_leave_the_screener_rows_alone() -> None:
    ev = run(build_world(), edge(frozen_from="2026-09-04"))
    frame = edge_eval_frame(ev, "r1", AS_OF)
    drawn = frame[frame["role"] == "random"]
    assert len(drawn) == 2000 and set(drawn["slice_kind"]) == {"draw"}  # uniform + sector-matched
    assert set(drawn["variant"]) == {"random:momo", "random_sector:momo"}
    assert drawn["decile_mean_01"].isna().all()
    screener = frame[(frame["role"] != "random") & (frame["slice_kind"] == "all")]
    assert screener.iloc[0]["decile_mean_01"] == pytest.approx(0.09)
    assert len(frame[frame["role"] != "random"]) == len(ev.results[0].measures) + 3 * 4  # + costs


def test_the_random_null_is_matched_to_the_screener_sessions_and_pick_counts() -> None:
    e = edge(frozen_from="2026-09-04", top_k=3)
    ev = run(build_world(no_features=[DAYS[4]]), e)  # the first out-of-sample start is lost
    frozen = next(m for m in ev.results[0].measures if m.slice_kind == "frozen")
    (found,) = uniform(ev)
    assert (found.variant, found.config_hash) == ("momo", ev.results[0].config_hash)
    first = found.draws[0]
    # Same sessions, picks (3 a session, not more), eligible names and base as the screener.
    assert (first.sessions, first.picks, first.eligible, first.base_hits) == (
        frozen.sessions,
        frozen.picks,
        frozen.eligible,
        frozen.base_hits,
    )
    assert frozen.sessions == 1 and frozen.picks == 3


def test_every_qualified_name_sizes_the_draws_when_top_k_is_all() -> None:
    ev = run(build_world(), edge(frozen_from="2026-09-04", top_k="all"))
    frozen = next(m for m in ev.results[0].measures if m.slice_kind == "frozen")
    (found,) = uniform(ev)
    assert found.draws[0].picks == frozen.picks > 0


def test_a_screener_that_held_nothing_keeps_the_sessions_base_in_its_draws(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real = session_reads.screen_variant

    def none_qualify(*a: Any, **k: Any) -> Any:
        return dataclasses.replace(real(*a, **k), qualified=())

    monkeypatch.setattr(session_reads, "screen_variant", none_qualify)
    ev = run(build_world(), edge(frozen_from="2026-09-04"))
    (found,) = uniform(ev)
    first = found.draws[0]
    assert (first.sessions, first.picks, first.hits) == (2, 0, 0)
    assert first.eligible == 40 and first.hit_rate is None


def test_the_run_hash_follows_the_random_draws() -> None:
    e = edge(frozen_from="2026-09-04")
    a = run(build_world(), e).run_hash
    b = evaluate_edge(
        build_world().reader, build_world().results, build_world().configs, USER, e,
        DAYS[0], DAYS[-1], AS_OF, random_draws=50,
    ).run_hash  # fmt: skip
    assert a != b


def test_a_block_with_a_day_the_screener_could_not_measure_has_no_draws_either() -> None:
    w = build_world(no_features=[DAYS[2]])  # the second day of the DAYS[1] block: no screen
    for day, names in {DAYS[1]: [10, 11], DAYS[2]: [12], DAYS[5]: [0, 1]}.items():
        w.write_reactions(day, {WORLD_IDS[i]: 0 for i in names})
    ev = run(w, event_edge(2, frozen_from="2026-09-01"))
    (found,) = uniform(ev)
    # Same sessions as the screener: the unmeasured block is in neither.
    frozen = next(m for m in ev.results[0].measures if m.slice_kind == "frozen")
    assert found.draws[0].sessions == frozen.sessions == 1
