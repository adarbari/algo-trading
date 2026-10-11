"""Random-pick draws: deterministic by (leg key, edge variant, holding period, session), the same
whatever order the names arrive in or range the run has, and measured like a screener's picks."""

from datetime import date, timedelta
from typing import Any

import numpy as np
import pandas as pd
import pytest

from algotrade.config.user import UserContext
from algotrade.services.evaluation.cross_section import measuring
from algotrade.services.evaluation.cross_section.harness import evaluate_edge
from algotrade.services.evaluation.cross_section.random_picks import (
    DRAW,
    RandomStat,
    generator,
    pool_random,
    random_measures,
    random_stat,
)
from tests.unit.services.evaluation.cross_section.conftest import AS_OF, DAYS, build_world, edge

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
