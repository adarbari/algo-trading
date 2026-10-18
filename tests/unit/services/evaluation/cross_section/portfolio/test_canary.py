"""The canary of a portfolio_return book (ADR 0074 amendment, item 17) measured end to end: the
canaries' field is read at D (never at S), the share that is negative, in units of ``breadth``,
moves that share of the book to the defensive asset (``CASH``, or the defensive ticker with the
highest field), a missing canary or defensive value leaves the session out with its reason, and
the volatility target is measured on the book the canary left."""

from collections.abc import Callable
from datetime import date
from typing import Any

import pandas as pd
import pytest

from algotrade.config.user import UserContext
from algotrade.core.time.calendar import next_session, sessions_between
from algotrade.services.evaluation.cross_section.harness import EdgeEvaluation, evaluate_edge
from algotrade.services.evaluation.cross_section.measures import SessionStat
from tests.helpers.stored_frames import stamped
from tests.unit.services.evaluation.cross_section.conftest import (
    AS_OF,
    FEATURE,
    IDS,
    World,
    build_world,
    edge,
    outcome_row,
)

FIELD = "rollup.option_liquidity@v1.put_strike"  # stands in for a momentum score (signed here)
FIRST, LAST = date(2026, 9, 1), date(2026, 9, 10)
ALL = sessions_between(date(2026, 7, 20), next_session(LAST))
CANARY = {"tickers": ["N00", "N01"], "field": FIELD, "breadth": 2, "defensive": ["CASH"]}
BILL = 0.0378


def _world(
    value_of: Callable[[date, int], float | None] = lambda day, i: 0.01,
    skip_outcome: str | None = None,
) -> World:
    w = build_world(
        days=ALL,
        no_features=ALL,
        rows_of=lambda day: [
            outcome_row(iid, i, day, horizon_sessions=1)
            for i, iid in enumerate(IDS)
            if iid != skip_outcome
        ],
    )
    for day in ALL:
        rows = [
            {
                "instrument_id": iid,
                "underlying_price": 100.0 + 10 * i,
                "put_strike": value_of(day, i),
            }
            for i, iid in enumerate(IDS)
        ]
        w.write_rollup(FEATURE, day, rows)
    ts = pd.Timestamp(ALL[0], tz="UTC")
    curve = [
        {"instrument_id": "RATE:UST-1M", "ts": ts, "tenor": "1M", "tenor_days": 30,
         "rate_par": BILL, "rate_cont": BILL}
    ]  # fmt: skip
    day = date(2026, 7, 19)
    w.writer.write_table("rates/treasury", day, "r", stamped(curve, day, "r"))
    return w


def _book(w: World, canary: dict[str, Any] | None = None, **outcome: Any) -> EdgeEvaluation:
    doc = {
        "kind": "portfolio_return", "horizon_sessions": [1], "benchmark": "mix:N00=0.6,N01=0.4",
        "start_offset_sessions": 1, "cost_bps": 20, "canary": CANARY if canary is None else canary,
        **outcome,
    }  # fmt: skip
    e = edge(outcome={k: v for k, v in doc.items() if v})
    return evaluate_edge(w.reader, w.results, w.configs, UserContext("site"), e, FIRST, LAST, AS_OF)


def _first(r: EdgeEvaluation) -> SessionStat:
    return r.results[0].stats[0]


def _bad(*names: int) -> Callable[[date, int], float | None]:
    return lambda day, i: -0.01 if i in names else 0.01


def test_every_canary_positive_leaves_the_book_whole() -> None:
    stat = _first(_book(_world()))
    assert stat.risk_off == 0.0
    assert dict(stat.weights) == pytest.approx({f"EQ:N{i}": 0.2 for i in range(15, 20)})


def test_the_share_of_negative_canaries_in_breadths_goes_to_cash() -> None:
    stat = _first(_book(_world(_bad(0))))  # one of two negative, breadth 2: half the book
    weights = dict(stat.weights)
    assert stat.risk_off == 0.5
    assert weights == pytest.approx({**{f"EQ:N{i}": 0.1 for i in range(15, 20)}, "CASH": 0.5})
    # with a breadth of 1 one negative canary is enough for the whole book
    whole = _first(_book(_world(_bad(0)), canary={**CANARY, "breadth": 1}))
    assert whole.risk_off == 1.0 and dict(whole.weights) == {"CASH": 1.0}
    both = _first(_book(_world(_bad(0, 1))))
    assert both.risk_off == 1.0 and dict(both.weights) == {"CASH": 1.0}


def test_a_defensive_ticker_is_the_one_with_the_highest_field_at_d() -> None:
    canary = {**CANARY, "defensive": ["N03", "N02", "N04"]}
    values = lambda day, i: {0: -0.01, 1: -0.01, 2: 0.02, 3: 0.05, 4: 0.05}.get(i, 0.01)  # noqa: E731
    stat = _first(_book(_world(values), canary=canary))
    weights = dict(stat.weights)  # N03 and N04 tie: the ticker order decides
    assert weights == pytest.approx({"EQ:N03": 1.0}) and stat.risk_off == 1.0


def test_the_canary_is_read_at_d_never_at_s() -> None:
    """The field turns negative only from the entry session S (the day after D) onwards: the
    book formed at D does not follow it."""
    calm = _first(_book(_world()))
    flipped = _first(_book(_world(lambda day, i: -0.01 if day > FIRST and i < 2 else 0.01)))
    assert flipped.risk_off == 0.0 and dict(flipped.weights) == dict(calm.weights)
    later = _book(_world(lambda day, i: -0.01 if day >= FIRST and i < 2 else 0.01)).results[0]
    assert later.stats[0].risk_off == 1.0  # on D itself it does


@pytest.mark.parametrize(
    ("canary", "value_of", "reason"),
    [
        ({"tickers": ["N00", "ZZZ"]}, None, "no_canary:ZZZ"),  # not an instrument at D
        ({}, lambda day, i: None if i == 1 else 0.01, "no_canary:N01"),  # no value
        (
            {"defensive": ["N02", "N03"]},
            lambda day, i: -0.01 if i < 2 else (None if i == 3 else 0.01),
            "no_defensive:N03",
        ),
    ],
)
def test_a_missing_canary_or_defensive_value_leaves_the_session_out(
    canary: dict[str, Any], value_of: Any, reason: str
) -> None:
    stat = _first(_book(_world(value_of or (lambda day, i: 0.01)), canary={**CANARY, **canary}))
    assert stat.portfolio_reason == reason and stat.weights == ()


def test_a_defensive_asset_with_no_return_at_s_is_no_pick_return() -> None:
    canary = {**CANARY, "defensive": ["N05"]}
    values = lambda day, i: -0.01 if i < 2 else 0.01  # noqa: E731
    stat = _first(_book(_world(values, skip_outcome=IDS[5]), canary=canary))
    assert stat.portfolio_reason == "no_pick_return"


def test_the_volatility_target_sees_the_book_the_canary_left() -> None:
    """With every canary negative the book is all cash: nothing to measure, nothing to scale."""
    stat = _first(_book(_world(_bad(0, 1)), vol_target=0.04, vol_window=20, vol_return_field=FIELD))
    assert stat.risk_off == 1.0 and stat.book_vol is None and dict(stat.weights) == {"CASH": 1.0}


def test_the_canary_is_part_of_the_trial() -> None:
    w = _world()
    assert _book(w).run_hash != _book(w, canary={**CANARY, "breadth": 1}).run_hash
    assert _book(w).run_hash == _book(w).run_hash
