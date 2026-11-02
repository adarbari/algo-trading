"""The share path walker (ADR 0088, E3c) on a hand-computed bars fixture: first exit in declared
order wins, exits at closes, a catalogue-field rule acts one close later, an UNKNOWN rule never
fires, a setup with no exit rule runs to its horizon, and the walks map to ``TRADE_COLUMNS``."""

from datetime import date, timedelta

import pandas as pd
import pytest

from algotrade.config.edges.positions.spec import ExitSettings, share_exit_rules
from algotrade.config.strategy.schema import Group, Rule
from algotrade.engines.structures.share_walk import ShareClose, walk_share
from algotrade.services.evaluation.evidence.contract import trade_problems
from algotrade.services.evaluation.evidence.shapes import share_path_trades

DAY = date(2026, 1, 5)


def closes(*prices: float, **extra: list[float | None]) -> list[ShareClose]:
    return [
        ShareClose(DAY + timedelta(i + 1), p, {k: v[i] for k, v in extra.items()} or None)
        for i, p in enumerate(prices)
    ]


def walk(side: str, exit: ExitSettings | None, *prices: float, horizon: int = 0, **extra):  # type: ignore[no-untyped-def]
    return walk_share(side, DAY, 100.0, closes(*prices, **extra), share_exit_rules(exit, side),
                      horizon or len(prices))  # fmt: skip


def test_take_profit_exits_at_the_close_that_crosses_it() -> None:
    w = walk("long", ExitSettings(take_profit=0.10, stop_loss=0.05), 102, 111, 130)
    assert (w.exit_kind, w.exit_index, w.exit_session) == ("TAKE_PROFIT", 2, DAY + timedelta(2))  # type: ignore[union-attr]
    assert w.gross_return == pytest.approx(0.11)  # the close, not the 10% level  # type: ignore[union-attr]


def test_stop_loss_and_the_short_side_direction() -> None:
    w = walk("long", ExitSettings(take_profit=0.5, stop_loss=0.05), 98, 94, 120)
    assert (w.exit_kind, w.gross_return, w.max_adverse) == (
        "STOP_LOSS",
        pytest.approx(-0.06),
        pytest.approx(0.06),
    )  # type: ignore[union-attr]
    s = walk("short", ExitSettings(take_profit=0.05, stop_loss=0.2), 99, 94, 80)
    assert (s.exit_kind, s.gross_return, s.max_adverse) == (
        "TAKE_PROFIT",
        pytest.approx(0.06),
        None,
    )  # type: ignore[union-attr]


def test_first_in_declared_order_wins_at_one_close() -> None:
    when = Group("all", (Rule("position.days_held", "gte", 1),))
    w = walk("long", ExitSettings(take_profit=0.01, when=when), 105, 106)
    assert w.exit_kind == "TAKE_PROFIT"  # type: ignore[union-attr]


def test_catalogue_when_acts_one_close_after_and_unknown_never_fires() -> None:
    when = Group("all", (Rule("feature.rsi_14", "gt", 70),))
    rules = ExitSettings(when=when)
    w = walk("long", rules, 101, 102, 103, 104, **{"feature.rsi_14": [75.0, 10.0, 10.0, 10.0]})
    assert (w.exit_kind, w.exit_index) == ("CONDITION", 2)  # type: ignore[union-attr]
    u = walk("long", rules, 101, 102, 103, **{"feature.rsi_14": [None, None, None]})
    assert (u.exit_kind, u.exit_index, u.unknown_closes) == ("HORIZON", 3, 2)  # type: ignore[union-attr]


def test_no_exit_is_the_horizon_return_and_short_history_is_delisted() -> None:
    w = walk("long", None, 90, 120, 110)
    assert (w.exit_kind, w.gross_return, w.underlying_return) == (
        "HORIZON",
        pytest.approx(0.10),
        pytest.approx(0.10),
    )  # type: ignore[union-attr]
    d = walk_share("long", DAY, 100.0, closes(90, 80), (), 5, delisted=True)
    assert (d.exit_kind, d.exit_index) == ("DELISTED", 2)  # type: ignore[union-attr]
    assert walk("long", None, 90, 80, horizon=5) is None  # a gap or a window not yet elapsed
    assert walk_share("long", DAY, 100.0, [], (), 5) is None
    assert walk_share("long", DAY, 0.0, closes(1.0), (), 1) is None


def test_walks_map_to_the_trade_contract() -> None:
    w = walk("long", ExitSettings(stop_loss=0.05), 94, 99)
    frame = pd.DataFrame(
        [
            {
                "instrument_id": "EQ:X",
                "exit_session": w.exit_session,
                "exit_kind": w.exit_kind,  # type: ignore[union-attr]
                "exit_index": w.exit_index,
                "gross_return": w.gross_return,
                "underlying_return": w.underlying_return,  # type: ignore[union-attr]
                "max_adverse": w.max_adverse,
            }
        ]
    )  # type: ignore[union-attr]
    trades = share_path_trades(frame, entry=DAY, side="long", cost_bps=10.0)
    assert trade_problems(trades) == []
    row = trades.iloc[0]
    assert (row["exit_kind"], row["capital_basis"], row["price_source"]) == (
        "STOP_LOSS",
        "notional",
        "bars",
    )
    assert row["return_on_capital"] == pytest.approx(-0.06 - 0.001)
    assert not row["hit"]


def test_a_bad_close_after_the_exit_does_not_drop_the_name() -> None:
    stop = ExitSettings(stop_loss=0.05)
    assert walk("long", stop, 94, float("nan"), 99).exit_kind == "STOP_LOSS"  # type: ignore[union-attr]
    assert walk("long", stop, 99, float("nan"), 99) is None  # bad before any exit is known


def test_a_short_pays_the_borrow_over_its_days_held() -> None:
    w = walk("short", None, 99, 98)
    frame = pd.DataFrame(
        [
            {
                "instrument_id": "EQ:X",
                "exit_session": w.exit_session,
                "exit_index": w.exit_index,  # type: ignore[union-attr]
                "exit_kind": w.exit_kind,
                "gross_return": w.gross_return,  # type: ignore[union-attr]
                "underlying_return": w.underlying_return,
                "max_adverse": None,
            }
        ]
    )  # type: ignore[union-attr]
    row = share_path_trades(
        frame, entry=DAY, side="short", cost_bps=0.0, borrow_bps_annual=252.0
    ).iloc[0]
    assert row["return_on_capital"] == pytest.approx(0.02 - 252e-4 * 2 / 252)
