"""The mapping of each outcome shape to the trade contract (ADR 0088, 2.5a), by hand: a share
and an option fixture give the same columns; the return on capital of every shape of the table;
a figure not known is null, never 0; the book is for the evidence only."""

import ast
from dataclasses import replace
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest

from algotrade.config.edges.positions.key import position_key
from algotrade.core.model.errors import ConfigurationError
from algotrade.services.evaluation.cross_section.hit import apply_outcome, short_view
from algotrade.services.evaluation.evidence import shapes
from algotrade.services.evaluation.evidence.contract import (
    COLUMN_NAMES,
    capital_basis_of,
    trade_problems,
)
from algotrade.services.evaluation.evidence.shapes import book_trades, series_trades, trade_frame
from tests.unit.services.evaluation.cross_section.conftest import IDS, edge, outcome_row

DAY, EXIT = date(2026, 9, 11), date(2026, 9, 15)
CHAIN = {
    "kind": "option_pnl", "horizon_sessions": [2], "benchmark": "none", "tenor_days": 30,
    "position": "short_put", "strike_delta": 0.25, "start_offset_sessions": 1,
}  # fmt: skip


def _outcome(**changes: Any) -> dict[str, Any]:
    return {"kind": "excess_return", "horizon_sessions": [2], "benchmark": "SPY",
            "start_offset_sessions": 1, **changes}  # fmt: skip


def _rows(n: int = 4, **changes: Any) -> pd.DataFrame:
    return pd.DataFrame([outcome_row(IDS[i], i + 10, DAY, **changes) for i in range(n)])


def _share(rows: pd.DataFrame | None = None, side: str = "long", **outcome: Any) -> pd.DataFrame:
    e = edge(outcome=_outcome(**({"side": side} if side == "short" else {}), **outcome))
    rows = _rows() if rows is None else rows
    res = apply_outcome(e, rows)
    view = short_view(res) if side == "short" else res
    return trade_frame(e, rows, view, entry=DAY, bars_exit=EXIT, side=side)


def _option_rows(**changes: Any) -> pd.DataFrame:
    key = position_key(edge(outcome=CHAIN).outcome, 2)
    rows = [
        {
            "instrument_id": IDS[i],
            "horizon_sessions": 2,
            "position_key": key,
            "outcome_status": "COMPLETE",
            "outcome_reason": None,
            "entry_spot": 100.0,
            "entry_half_spread": 0.2,
            "exit_half_spread": 0.1,
            "pnl_mid": 2.0 + i,
            "exit_unknown_closes": 0,
            "collateral": 90.0,
            "max_adverse": 0.04,
            "exit_session": date(2026, 9, 14),
            "exit_kind": "TAKE_PROFIT",
            "price_source": "cboe",
            "licence": "open",
            **changes,
        }
        for i in range(3)
    ]
    return pd.DataFrame(rows).assign(
        fwd_return=np.nan, fwd_excess_return=np.nan, fwd_max_return=np.nan,
        fwd_max_drawdown=np.nan, fwd_realised_vol=np.nan,
    )  # fmt: skip


def _option(rows: pd.DataFrame | None = None, **outcome: Any) -> pd.DataFrame:
    e = edge(outcome={**CHAIN, **outcome})
    rows = _option_rows() if rows is None else rows
    return trade_frame(e, rows, apply_outcome(e, rows), entry=DAY, bars_exit=EXIT, side="long")


def test_share_and_option_frames_have_the_contract_columns() -> None:
    for frame in (_share(), _option()):
        assert list(frame.columns) == list(COLUMN_NAMES)
        assert trade_problems(frame) == []


def test_a_share_long_pick_by_hand() -> None:
    f = _share(cost_bps=20)
    first = f.iloc[0]  # name 10: fwd_return = 0.005, excess the same
    assert (first["capital_basis"], first["price_source"], first["exit_kind"]) == (
        "notional", "bars", "HORIZON",
    )  # fmt: skip
    assert first["return_on_capital_gross"] == pytest.approx(0.005)
    assert first["return_on_capital"] == pytest.approx(0.005 - 0.002)
    assert first["value"] == pytest.approx(0.005 - 0.002)
    assert (first["entry_session"], first["exit_session"]) == (DAY, EXIT)
    assert first["underlying_return"] == pytest.approx(0.005) and first["max_adverse"] == 0.0
    assert bool(first["hit"]) and first["outcome_licence"] == "open" and np.isnan(first["capital"])


def test_a_delisted_name_exits_as_delisted() -> None:
    f = _share(_rows(outcome_status="DELISTED"))
    assert set(f["exit_kind"]) == {"DELISTED"} and f["delisted"].all()


def test_a_short_pick_pays_the_borrow_and_has_no_adverse() -> None:
    f = _share(side="short", cost_bps=20, borrow_bps_annual=252)
    first = f.iloc[0]
    borrow = 0.0252 * 2 / 252
    assert first["side"] == "short"
    assert first["return_on_capital_gross"] == pytest.approx(-0.005)
    assert first["return_on_capital"] == pytest.approx(-0.005 - 0.002 - borrow)
    assert np.isnan(first["max_adverse"]) and first["underlying_return"] == pytest.approx(0.005)


def test_a_non_finite_return_is_null_never_zero() -> None:
    rows = _rows()
    rows.loc[0, "fwd_return"] = np.nan
    rows.loc[0, "fwd_excess_return"] = np.nan
    f = _share(rows)
    first = f.iloc[0]
    assert first["excluded"] == "missing_value"
    assert (
        first[["value", "return_on_capital", "return_on_capital_gross", "underlying_return"]]
        .isna()
        .all()
    )
    assert pd.isna(first["exit_kind"]) and trade_problems(f) == []


def test_an_expires_otm_or_hit_target_has_no_capital_and_no_return() -> None:
    target = {"kind": "hit_target", "target": 0.0, "measure": "excess_return", "direction": "above"}
    f = _share(**target)
    assert set(f["capital_basis"]) == {"none"}
    assert (
        f[["capital", "return_on_capital", "return_on_capital_gross", "max_adverse"]]
        .isna()
        .all()
        .all()
    )
    assert f["underlying_return"].notna().all() and set(f["price_source"]) == {"bars"}


def test_the_model_pnl_is_priced_by_the_model_on_the_notional() -> None:
    e = edge(outcome={"kind": "option_model_pnl", "horizon_sessions": [21], "benchmark": "none",
                      "start_offset_sessions": 1, "structure": "atm_straddle_long",
                      "iv_field": "rollup.ibkr_iv@v1.iv30_ibkr", "cost_bps": 10},
             schedule="every_session")  # fmt: skip
    rows = _rows(horizon_sessions=21)
    iv = dict.fromkeys(IDS, 0.2)
    res = apply_outcome(e, rows, iv)
    f = trade_frame(e, rows, res, entry=DAY, bars_exit=EXIT, side="long")
    assert (set(f["price_source"]), set(f["capital_basis"])) == ({"model"}, {"notional"})
    counted = f[f["excluded"] == ""]
    assert (counted["return_on_capital_gross"] - counted["value"]).tolist() == pytest.approx(
        [0.001] * len(counted)
    )


def test_a_pair_is_one_row_with_both_legs_costs() -> None:
    e = edge(outcome={"kind": "pair_spread", "horizon_sessions": [2], "benchmark": "none",
                      "pair_field": "rollup.share_classes@v1.sibling_id", "cost_bps": 10,
                      "borrow_bps_annual": 252, "start_offset_sessions": 1})  # fmt: skip
    value = 0.01
    res = pd.DataFrame({"instrument_id": [IDS[0]], "value": [value], "oriented": [value],
                        "hit": [True], "excluded": [""], "delisted": [False]})  # fmt: skip
    f = trade_frame(e, _rows(1), res, entry=DAY, bars_exit=EXIT, side="long")
    assert len(f) == 1 and f.loc[0, "return_on_capital"] == value
    assert f.loc[0, "return_on_capital_gross"] == pytest.approx(
        value + 2 * 0.001 + 0.0252 * 2 / 252
    )


def test_an_option_trade_by_hand() -> None:
    f = _option(cost_bps=10)
    first = f.iloc[0]  # pnl_mid 2, half-spreads 0.2 + 0.1, spot 100, collateral 90
    assert first["capital_basis"] == edge(outcome=CHAIN).outcome.position.collateral
    assert first["capital"] == 90.0
    assert first["return_on_capital_gross"] == pytest.approx(2.0 / 90)
    assert first["return_on_capital"] == pytest.approx((2.0 - 0.3 - 0.001 * 100) / 90)
    assert first["return_on_capital"] == pytest.approx(first["value"] * 100 / 90)
    assert (first["exit_session"], first["exit_kind"]) == (date(2026, 9, 14), "TAKE_PROFIT")
    assert (first["price_source"], first["max_adverse"]) == ("cboe", 0.04)
    assert np.isnan(first["underlying_return"])


def test_an_option_licence_and_source_come_from_the_row() -> None:
    f = _option(_option_rows(price_source="option_history", licence="personal"))
    assert set(f["price_source"]) == {"option_history"} and set(f["outcome_licence"]) == {
        "personal"
    }


@pytest.mark.parametrize("collateral", [None, 0.0, -5.0, float("inf")])
def test_no_collateral_gives_no_return_but_the_row_still_counts(collateral: float | None) -> None:
    f = _option(_option_rows(collateral=collateral))
    assert f[["capital", "return_on_capital", "return_on_capital_gross"]].isna().all().all()
    assert (f["excluded"] == "").all() and f["value"].notna().all() and trade_problems(f) == []


def test_an_unmeasured_option_trade_has_no_figures() -> None:
    rows = _option_rows(outcome_status="UNMEASURED", outcome_reason="NO_CHAIN:2026-09-11")
    rows["pnl_mid"] = np.nan
    rows["exit_session"] = None
    rows["exit_kind"] = None
    f = _option(rows)
    assert set(f["excluded"]) == {"unmeasured"}
    assert f[["value", "capital", "return_on_capital", "max_adverse"]].isna().all().all()
    assert f["exit_session"].isna().all() and trade_problems(f) == []


def test_an_option_edge_with_no_collateral_rule_has_no_capital_basis() -> None:
    e = edge(outcome=CHAIN)
    bare = replace(
        e, outcome=replace(e.outcome, position=replace(e.outcome.position, collateral=""))
    )
    with pytest.raises(ConfigurationError, match="collateral"):
        capital_basis_of(bare)


def test_a_book_has_no_name_by_name_basis() -> None:
    e = edge(outcome=_outcome(kind="portfolio_return", horizon_sessions=[1], cost_bps=20))
    with pytest.raises(ConfigurationError):
        capital_basis_of(e)


def test_a_chain_partition_with_several_position_keys_maps_its_own_key() -> None:
    rows = pd.concat([_option_rows(), _option_rows(position_key="other", pnl_mid=99.0)])
    f = _option(rows)
    assert len(f) == 3 and f["return_on_capital_gross"].max() < 1


def test_the_mapping_is_deterministic() -> None:
    pd.testing.assert_frame_equal(_share(cost_bps=20), _share(cost_bps=20))
    pd.testing.assert_frame_equal(_option(), _option())


def test_series_trades_are_the_windows_returns() -> None:
    e = edge()
    rows = _rows()
    rows.loc[1, "fwd_return"] = -0.01
    f = series_trades(e, rows.assign(session_date=pd.Timestamp(DAY)))
    assert list(f.columns) == list(COLUMN_NAMES) and trade_problems(f) == []
    assert f["value"].tolist() == pytest.approx(rows["fwd_return"].tolist())
    assert f["hit"].tolist() == [True, False, True, True]
    assert (f["return_on_capital"] == f["value"]).all() and (f["entry_session"] == DAY).all()
    assert series_trades(e, rows.iloc[:0]).empty


def _series(**changes: Any) -> pd.DataFrame:
    row = {"role": "screener", "status": "measured", "entry_session": DAY, "exit_session": EXIT,
           "pick_mean": 0.012, **changes}  # fmt: skip
    return pd.DataFrame([row, {**row, "role": "random", "pick_mean": 0.5},
                         {**row, "status": "excluded_coverage", "pick_mean": None}])  # fmt: skip


def test_book_trades() -> None:
    f = book_trades(_series())
    assert len(f) == 1  # the screener's measured block only
    row = f.iloc[0]
    assert (row["instrument_id"], row["capital_basis"], row["exit_kind"]) == (
        "BOOK",
        "book",
        "HORIZON",
    )
    assert row["return_on_capital"] == row["return_on_capital_gross"] == row["value"] == 0.012
    assert trade_problems(f) == []
    assert book_trades(_series(role="random")).empty


def test_no_ledger_module_imports_the_book() -> None:
    root = Path(shapes.__file__).parents[1] / "cross_section" / "detail"
    for path in root.glob("*.py"):
        text = ast.dump(ast.parse(path.read_text()))
        assert "book_trades" not in text, path
