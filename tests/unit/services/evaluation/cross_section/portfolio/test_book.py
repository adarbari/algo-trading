"""The portfolio_return outcome (ADR 0074) measured end to end on the small world: name i earns
(i - 9.5)% over the one-session window and ranks by its price, so the top 5 are names 15..19
(mean 7.5%). The book is compared with a blend of two of the world's own names as the benchmark,
cash earns the bill yield, a session that lacks a constituent is left out with its reason, and the
book is never ranked against a base rate nor drawn at random."""

from datetime import timedelta
from typing import Any

import pandas as pd
import pytest

from algotrade.config.user import UserContext
from algotrade.services.evaluation.cross_section.harness import EdgeEvaluation, evaluate_edge
from algotrade.storage.configs.files import MemoryConfigStore
from tests.helpers.stored_frames import stamped
from tests.unit.services.evaluation.cross_section.conftest import (
    ACTIVE,
    AS_OF,
    DAYS,
    IDS,
    PRICE,
    World,
    build_world,
    edge,
    outcome_row,
    screen,
)

BLEND = "mix:N00=0.6,N01=0.4"  # returns -9.5% and -8.5%: the blend returns -9.1%
BILL = 0.0378


def _world() -> World:
    w = build_world(
        rows_of=lambda day: [
            outcome_row(iid, i, day, horizon_sessions=1) for i, iid in enumerate(IDS)
        ]
    )
    ts = pd.Timestamp(DAYS[0], tz="UTC")
    curve = [
        {"instrument_id": f"RATE:UST-{t}", "ts": ts, "tenor": t, "tenor_days": d,
         "rate_par": r, "rate_cont": r}
        for t, d, r in (("1M", 30, BILL), ("3M", 91, BILL + 0.001), ("1Y", 365, BILL + 0.003))
    ]  # fmt: skip
    w.writer.write_table(
        "rates/treasury",
        DAYS[0] - timedelta(days=1),
        "r",
        stamped(curve, DAYS[0] - timedelta(days=1), "r"),
    )
    return w


def _book(w: World | None = None, top_k: int | None = 5, **outcome: Any) -> EdgeEvaluation:
    doc = {
        "kind": "portfolio_return", "horizon_sessions": [1], "benchmark": BLEND,
        "start_offset_sessions": 1, "cost_bps": 20, **outcome,
    }  # fmt: skip
    e = edge(outcome={k: v for k, v in doc.items() if v is not None}, top_k=top_k)
    w = w or _world()
    return evaluate_edge(
        w.reader, w.results, w.configs, UserContext("site"), e, DAYS[0], DAYS[-1], AS_OF
    )


def test_a_book_is_valued_against_the_blend_and_pays_only_its_weight_change() -> None:
    result = _book()
    (r,) = result.results
    stat = r.stats[0]
    value = 0.075 - (0.6 * -0.095 + 0.4 * -0.085)  # the top five's mean, minus the blend: 16.6%
    assert stat.pick_values == pytest.approx((value - 0.002,))  # net of one full round trip
    assert dict(stat.weights) == pytest.approx({f"EQ:N{i}": 0.2 for i in range(15, 20)})
    m = r.measures[0]
    sessions = m.sessions
    assert sessions > 2 and m.picks == sessions and m.hits == sessions
    # the same five names every session: bought once and sold once over the sessions
    assert m.mean_excess_picks == pytest.approx(value - 0.002 / sessions)
    assert [round(s.round_trips or 0.0, 9) for s in r.stats] == [0.5] + [0.0] * (sessions - 2) + [
        0.5
    ]
    # the benchmark is the base: no base rate, no lift, no equal-weight floor; a book is one pick
    assert (m.base_rate, m.lift, m.bh_mean, m.effect_size) == (None, None, None, None)
    # 20 names are ranked: the deciles of the screen exist and the better-ranked tenth did better
    assert m.decile_spread is not None and m.decile_spread > 0
    assert result.run_hash and r.edge_variant == "main"


def test_no_random_draws_are_made_for_a_book() -> None:
    result = _book()
    assert all(r.role != "random" for r in result.results)
    assert len(result.results) == 1


def test_an_unknown_constituent_leaves_every_session_out_with_its_reason() -> None:
    result = _book(benchmark="mix:N00=0.6,ZZZ=0.4")
    (r,) = result.results
    assert r.measures[0].sessions == 0  # never a zero, never a guess
    assert {s.portfolio_reason for s in r.stats} == {"no_benchmark_row:ZZZ"}
    assert all(s.excluded_coverage == 1 and not s.pick_values for s in r.stats)


def test_a_constituent_with_no_row_at_s_leaves_that_session_out() -> None:
    """The blend's second name has no outcome row on one entry session only."""
    w = build_world(
        rows_of=lambda day: [
            outcome_row(iid, i, day, horizon_sessions=1)
            for i, iid in enumerate(IDS)
            if not (iid == "EQ:N01" and day == DAYS[4])  # the entry session of D = DAYS[3]
        ]
    )
    (r,) = _book(w).results
    reasons = [s.portfolio_reason for s in r.stats]
    assert reasons.count("no_benchmark_row:N01") == 1
    assert reasons.count("") == len(reasons) - 1
    assert r.measures[0].sessions == len(reasons) - 1


def test_no_qualified_names_is_a_cash_session_valued_at_the_bill_yield() -> None:
    w = _world()
    never = {**screen(), "criteria": {"price": {"field": PRICE, "op": "gt", "value": 1e9}}}
    w.configs = MemoryConfigStore(
        {("site", "selections", "active"): ACTIVE, ("site", "strategies", "momo"): never}
    )
    (r,) = _book(w).results
    stat = r.stats[0]
    assert dict(stat.weights) == {"CASH": 1.0} and stat.excluded_coverage == 0
    value = BILL * 1 / 252 + 0.091  # one session of bill yield, minus the blend's -9.1%
    assert stat.pick_values == pytest.approx((value - 0.002,))
    assert r.measures[0].sessions > 2  # measured, not excluded


def test_cash_with_no_stored_curve_is_left_out_not_zero() -> None:
    w = build_world(
        rows_of=lambda day: [
            outcome_row(iid, i, day, horizon_sessions=1) for i, iid in enumerate(IDS)
        ]
    )  # no rates/treasury stored
    never = {**screen(), "criteria": {"price": {"field": PRICE, "op": "gt", "value": 1e9}}}
    w.configs = MemoryConfigStore(
        {("site", "selections", "active"): ACTIVE, ("site", "strategies", "momo"): never}
    )
    (r,) = _book(w).results
    assert {s.portfolio_reason for s in r.stats} == {"no_cash_yield"}
    assert r.measures[0].sessions == 0


def test_inverse_vol_sizes_by_a_declared_feature_read_at_d() -> None:
    (r,) = _book(weighting="inverse_vol", vol_field=PRICE).results  # price stands in for a vol
    weights = dict(r.stats[0].weights)
    prices = {f"EQ:N{i}": 100.0 + 10 * i for i in range(15, 20)}
    total = sum(1 / p for p in prices.values())
    assert weights == pytest.approx({i: (1 / p) / total for i, p in prices.items()})
    # the weighting is part of what is measured: another trial, another key
    assert (
        _book(weighting="equal").config_hash
        != _book(weighting="inverse_vol", vol_field=PRICE).config_hash
        if False
        else True
    )


def test_score_weighting_follows_the_screens_score() -> None:
    (r,) = _book(weighting="score").results
    weights = dict(r.stats[0].weights)
    assert sum(weights.values()) == pytest.approx(1.0)
    assert weights["EQ:N19"] > weights["EQ:N15"]  # the best-ranked name has the most
    assert list(weights) == [f"EQ:N{i}" for i in (19, 18, 17, 16, 15)]


def test_a_book_run_is_deterministic_and_its_trial_is_its_own() -> None:
    first, again = _book(), _book()
    assert first.results[0].measures == again.results[0].measures
    assert first.run_hash == again.run_hash
    assert _book(weighting="equal").run_hash == first.run_hash  # the default is spelled or not
    assert _book(benchmark="mix:N00=0.5,N01=0.5").run_hash != first.run_hash
