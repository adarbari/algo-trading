"""A volatility-targeted portfolio_return book (ADR 0074 amendment) measured end to end: the book
is scaled down by ``target / sigma`` with the rest in cash, sigma coming from the daily returns of
today's weights over the window as each of those days read them; a session whose window lacks a
return is left out with its reason, an all-cash book is not scaled, and nothing after the decision
session moves the scale."""

from datetime import date, timedelta
from typing import Any

import numpy as np
import pandas as pd
import pytest

from algotrade.config.user import UserContext
from algotrade.core.time.calendar import next_session, sessions_between, sessions_ending
from algotrade.services.evaluation.cross_section.harness import EdgeEvaluation, evaluate_edge
from algotrade.services.evaluation.cross_section.portfolio.overlays import NO_BOOK_VOL
from algotrade.storage.configs.files import MemoryConfigStore
from tests.helpers.stored_frames import stamped
from tests.unit.services.evaluation.cross_section.conftest import (
    ACTIVE,
    AS_OF,
    FEATURE,
    IDS,
    PRICE,
    World,
    build_world,
    edge,
    outcome_row,
    screen,
)

RET = "rollup.option_liquidity@v1.put_strike"  # stands in for the stored daily return
FIRST, LAST = date(2026, 9, 1), date(2026, 9, 10)
ALL = sessions_between(date(2026, 7, 20), next_session(LAST))
BILL = 0.0378
TARGET = 0.04
UNTARGETED = {"vol_target": None, "vol_window": None, "vol_return_field": None}


def _daily(day: date) -> float:
    """The daily return every name earns on ``day``: alternating 1% and 2%, so sigma is known."""
    return 0.01 + 0.01 * (day.toordinal() % 2)


def _world(
    ret_of: Any = None, skip: tuple[date, str] | None = None, spike: dict[date, float] | None = None
) -> World:
    w = build_world(
        days=ALL,
        no_features=ALL,
        rows_of=lambda day: [
            outcome_row(iid, i, day, horizon_sessions=1) for i, iid in enumerate(IDS)
        ],
    )
    for day in ALL:
        value = (spike or {}).get(day, (ret_of or _daily)(day))
        rows = [
            {"instrument_id": iid, "underlying_price": 100.0 + 10 * i, "put_strike": value}
            for i, iid in enumerate(IDS)
            if skip != (day, iid)
        ]
        w.write_rollup(FEATURE, day, rows)
    ts = pd.Timestamp(ALL[0], tz="UTC")
    curve = [
        {"instrument_id": "RATE:UST-1M", "ts": ts, "tenor": "1M", "tenor_days": 30,
         "rate_par": BILL, "rate_cont": BILL}
    ]  # fmt: skip
    day = ALL[0] - timedelta(days=1)
    w.writer.write_table("rates/treasury", day, "r", stamped(curve, day, "r"))
    return w


def _book(w: World, **outcome: Any) -> EdgeEvaluation:
    doc = {
        "kind": "portfolio_return", "horizon_sessions": [1], "benchmark": "mix:N00=0.6,N01=0.4",
        "start_offset_sessions": 1, "cost_bps": 20, "vol_target": TARGET, "vol_window": 20,
        "vol_return_field": RET, **outcome,
    }  # fmt: skip
    e = edge(outcome={k: v for k, v in doc.items() if v is not None}, top_k=5)
    return evaluate_edge(w.reader, w.results, w.configs, UserContext("site"), e, FIRST, LAST, AS_OF)


def _sigma(day: date) -> float:
    window = sessions_ending(day, 20)
    return float(np.std([_daily(d) for d in window], ddof=1) * np.sqrt(252))


def test_a_book_over_the_target_is_scaled_down_with_the_rest_in_cash() -> None:
    (r,) = _book(_world()).results
    stat = r.stats[0]
    sigma = _sigma(stat.session)
    k = TARGET / sigma
    assert 0 < k < 1 and stat.book_vol == pytest.approx(sigma)
    weights = dict(stat.weights)
    assert {i: w for i, w in weights.items() if i != "CASH"} == pytest.approx(
        {f"EQ:N{i}": 0.2 * k for i in range(15, 20)}
    )
    assert weights["CASH"] == pytest.approx(1 - k) and sum(weights.values()) == pytest.approx(1.0)
    # gross value: the names' mean return 7.5% scaled, cash at the bill yield over one session
    gross = k * 0.075 + (1 - k) * BILL / 252 - (0.6 * -0.095 + 0.4 * -0.085)
    assert stat.pick_values == pytest.approx((gross - 0.002,))


def test_a_target_above_the_volatility_leaves_the_book_as_the_weighting_formed_it() -> None:
    (r,) = _book(_world(), vol_target=1.0).results
    stat = r.stats[0]
    assert dict(stat.weights) == pytest.approx({f"EQ:N{i}": 0.2 for i in range(15, 20)})
    assert stat.book_vol == pytest.approx(_sigma(stat.session))  # measured, not applied


def test_scaling_is_turnover_so_it_pays_the_cost() -> None:
    """The scale moves from session to session (a window rolls), so the weight change is charged
    over the names; a book with no target holds the same five names and trades only twice."""
    scaled, plain = _book(_world()).results[0], _book(_world(), **UNTARGETED).results[0]
    trips = [s.round_trips or 0.0 for s in scaled.stats]
    base = [s.round_trips or 0.0 for s in plain.stats]
    assert any(t > 0 for t in trips[1:-1]) and not any(base[1:-1])
    assert plain.stats[0].book_vol is None


def test_a_missing_return_in_the_window_leaves_the_session_out_with_its_reason() -> None:
    day = sessions_ending(FIRST, 20)[0]  # the oldest day of the first session's window
    w = _world(skip=(day, IDS[17]))
    (r,) = _book(w).results
    held = {s.session: s for s in r.stats}
    assert held[FIRST].portfolio_reason == NO_BOOK_VOL and held[FIRST].weights == ()
    later = next(s for s in r.stats if day not in sessions_ending(s.session, 20))
    assert later.portfolio_reason == "" and later.weights  # the hole has left the window


def test_nothing_after_the_decision_session_moves_the_scale() -> None:
    """A huge return stored on S (the day after D) and later never enters the volatility."""
    calm = _book(_world()).results[0].stats
    spiked = _book(_world(spike={d: 9.0 for d in ALL if d > FIRST})).results[0].stats
    assert calm[0].book_vol == spiked[0].book_vol
    assert dict(calm[0].weights) == dict(spiked[0].weights)


def test_an_all_cash_book_has_nothing_to_scale() -> None:
    w = _world()
    never = {**screen(), "criteria": {"price": {"field": PRICE, "op": "gt", "value": 1e9}}}
    w.configs = MemoryConfigStore(
        {("site", "selections", "active"): ACTIVE, ("site", "strategies", "momo"): never}
    )
    (r,) = _book(w).results
    assert all(dict(s.weights) == {"CASH": 1.0} and s.book_vol is None for s in r.stats)


def test_the_target_is_part_of_the_trial() -> None:
    w = _world()
    assert _book(w).run_hash != _book(w, vol_target=0.05).run_hash
    assert _book(w).run_hash != _book(w, **UNTARGETED).run_hash
    assert _book(w).run_hash == _book(w).run_hash
