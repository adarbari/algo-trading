"""Random window sets: the same draws for the same inputs whatever the order observations arrive
in, as many periods per draw as the edge has windows, scored against the instrument's own
out-of-window share."""

from datetime import date

import pytest

from algotrade.services.evaluation.cross_section.random_picks import DEFAULT_DRAWS
from algotrade.services.evaluation.time_series.measures import Obs
from algotrade.services.evaluation.time_series.periods import Period
from algotrade.services.evaluation.time_series.random_windows import generator, random_windows


def pool() -> list[Obs]:
    out = []
    for i in range(30):
        day = date(2025, 1, 1 + i)
        inside = i % 5 == 0  # 6 windows
        out.append(Obs(Period(day, day, day, inside), 0.01 if inside else (-1) ** i * 0.002, "x"))
    return out


def test_a_thousand_seeded_draws_of_as_many_periods_as_windows() -> None:
    draws = random_windows(pool(), "tom|turn_of_month|SPY|4")
    assert len(draws) == DEFAULT_DRAWS == 1000
    base_hits = sum(o.value > 0 for o in pool() if not o.period.inside)
    for d in draws:
        assert (d.slice_kind, d.picks, d.sessions, d.eligible) == ("draw", 6, 6, 24)
        assert d.base_hits == base_hits and d.base_rate == pytest.approx(base_hits / 24)
        assert d.hit_rate == pytest.approx(d.hits / 6) and 0 <= d.hits <= 6
    assert [d.slice_value for d in draws[:3]] == ["0", "1", "2"]
    assert len({d.mean_excess_picks for d in draws}) > 10  # the draws differ


def test_the_draws_do_not_depend_on_the_order_observations_arrive_in() -> None:
    a = random_windows(pool(), "k", 50)
    b = random_windows(list(reversed(pool())), "k", 50)
    assert a == b
    assert random_windows(pool(), "other", 50) != a  # the key seeds them


def test_the_generator_is_a_function_of_its_key() -> None:
    assert generator("k").random() == generator("k").random()
    assert generator("k").random() != generator("j").random()


def test_no_window_no_base_or_too_few_periods_draw_nothing() -> None:
    only_out = [o for o in pool() if not o.period.inside]
    only_in = [o for o in pool() if o.period.inside]
    assert random_windows(only_out, "k") == () and random_windows(only_in, "k") == ()
    assert random_windows([], "k") == ()
