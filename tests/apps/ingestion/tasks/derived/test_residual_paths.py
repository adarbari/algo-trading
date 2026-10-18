"""The residual-return arithmetic on a hand-built panel with known answers: the return minus the
loadings times the factor returns of the window (size, momentum and value as ETF minus SPY), the
sector term only for a name with a sector loading, a DELISTED name measured over its own window,
and every gap an UNMEASURED row with its reason, never a market-only residual and never a zero."""

from datetime import date

import numpy as np
import pandas as pd
import pytest

from algotrade.core.time.calendar import sessions_ending
from algotrade_ingestion.tasks.derived.outcome_paths import Window, wide_closes
from algotrade_ingestion.tasks.derived.residual_paths import (
    COLUMNS,
    NO_BETAS,
    NO_FACTOR_BAR,
    NO_FACTOR_HISTORY,
    SHORT_HISTORY,
    residual_rows,
)

T = date(2026, 10, 2)
WINDOW = Window(tuple(sessions_ending(T, 5)))  # h = 4
BEFORE = date(2026, 9, 24)
ETF = {"SPY": "E:SPY", "IWM": "E:IWM", "MTUM": "E:MTUM", "VLUE": "E:VLUE", "XLK": "E:XLK"}
# end-of-window ETF returns: SPY +10%, IWM +15%, MTUM +12%, VLUE +8%, XLK +20%
ETF_CLOSES = {"E:SPY": 1.10, "E:IWM": 1.15, "E:MTUM": 1.12, "E:VLUE": 1.08, "E:XLK": 1.20}
BETAS = {"beta_mkt": 1.2, "beta_size": 0.5, "beta_mom": -0.3, "beta_value": 0.2}


def _closes(
    names: dict[str, list[float | None]], etfs: dict[str, float] | None = None
) -> pd.DataFrame:
    rows = []
    for iid, end in (etfs or ETF_CLOSES).items():
        ramp = np.linspace(1.0, end, len(WINDOW.sessions))
        names = {**names, iid: list(ramp)}
    for iid, series in names.items():
        for day, close in zip(WINDOW.sessions, series, strict=True):
            if close is not None:
                rows.append({"instrument_id": iid, "session_date": day, "close": close})
    return wide_closes(pd.DataFrame(rows), WINDOW, "close")


def _forward(*ids: str, ret: float = 0.30, status: str = "COMPLETE") -> pd.DataFrame:
    return pd.DataFrame(
        {"instrument_id": list(ids), "fwd_return": ret, "outcome_status": status,
         "outcome_reason": None}
    )  # fmt: skip


def _betas(rows: dict[str, dict[str, object]]) -> pd.DataFrame:
    base = {**BETAS, "beta_sector": np.nan, "factor_status": "NO_SECTOR", "sector_etf": None}
    return pd.DataFrame({i: {**base, **r} for i, r in rows.items()}).T.rename_axis("instrument_id")


def _run(names, forward, betas, etfs=None, etf=ETF) -> pd.DataFrame:
    out = residual_rows(forward, _closes(names, etfs), WINDOW, etf, betas, BEFORE)
    return out.set_index("instrument_id")


A = [1.0, 1.05, 1.1, 1.2, 1.3]


def test_the_residual_is_the_return_minus_the_loadings_times_the_factor_returns() -> None:
    out = _run({"EQ:A": A}, _forward("EQ:A"), _betas({"EQ:A": {}}))
    spy, iwm, mtum, vlue = 0.10, 0.15, 0.12, 0.08
    explained = 1.2 * spy + 0.5 * (iwm - spy) - 0.3 * (mtum - spy) + 0.2 * (vlue - spy)
    row = out.loc["EQ:A"]
    assert row["fwd_factor_return"] == pytest.approx(explained)
    assert row["fwd_residual_return"] == pytest.approx(0.30 - explained)
    assert row["outcome_status"] == "COMPLETE" and pd.isna(row["outcome_reason"])
    assert row["beta_session"] == BEFORE
    assert list(out.reset_index().columns) == list(COLUMNS)


def test_a_sector_loading_adds_the_sector_etf_minus_spy_and_only_then() -> None:
    sector = {"EQ:A": {"beta_sector": 0.4, "factor_status": "OK", "sector_etf": "XLK"}}
    out = _run({"EQ:A": A, "EQ:B": A}, _forward("EQ:A", "EQ:B"), _betas({**sector, "EQ:B": {}}))
    assert out.loc["EQ:A", "fwd_factor_return"] - out.loc["EQ:B", "fwd_factor_return"] == (
        pytest.approx(0.4 * (0.20 - 0.10))
    )  # B has no sector (NO_SECTOR): the four factors alone, still measured


def test_a_delisted_name_is_measured_over_its_own_window_not_the_full_one() -> None:
    dead = [1.0, 1.05, 1.1, None, None]  # last bar at row 2
    out = _run({"EQ:D": dead}, _forward("EQ:D", ret=0.10, status="DELISTED"), _betas({"EQ:D": {}}))
    spy = 1.0 + (0.10 * 2 / 4) - 1.0  # the ETF ramps are linear: row 2 of 4 is half the move
    iwm, mtum, vlue = 0.15 / 2, 0.12 / 2, 0.08 / 2
    explained = 1.2 * spy + 0.5 * (iwm - spy) - 0.3 * (mtum - spy) + 0.2 * (vlue - spy)
    assert out.loc["EQ:D", "fwd_residual_return"] == pytest.approx(0.10 - explained)
    assert out.loc["EQ:D", "outcome_status"] == "DELISTED"


def test_before_the_factor_etfs_exist_every_name_is_unmeasured_never_market_only() -> None:
    etfs = {k: v for k, v in ETF_CLOSES.items() if k not in ("E:MTUM", "E:VLUE")}
    out = _run({"EQ:A": A}, _forward("EQ:A"), _betas({"EQ:A": {}}), etfs=etfs)
    row = out.loc["EQ:A"]
    assert row["outcome_status"] == "UNMEASURED" and row["outcome_reason"] == NO_FACTOR_HISTORY
    assert pd.isna(row["fwd_residual_return"]) and pd.isna(row["fwd_factor_return"])


def test_a_factor_etf_the_reference_does_not_know_is_no_factor_history() -> None:
    etf = {k: v for k, v in ETF.items() if k != "VLUE"}
    out = _run({"EQ:A": A}, _forward("EQ:A"), _betas({"EQ:A": {}}), etf=etf)
    assert out.loc["EQ:A", "outcome_reason"] == NO_FACTOR_HISTORY


def test_missing_betas_are_unmeasured_with_the_betas_own_reason_never_zero() -> None:
    betas = _betas(
        {
            "EQ:SHORT": {"factor_status": "SHORT_HISTORY", "beta_mkt": np.nan, "beta_size": np.nan,
                         "beta_mom": np.nan, "beta_value": np.nan},
            "EQ:NOFAC": {"factor_status": "NO_FACTOR_HISTORY", "beta_mkt": np.nan},
            "EQ:NAN": {"factor_status": "OK", "beta_mkt": np.nan},
        }
    )  # fmt: skip
    names = dict.fromkeys(("EQ:SHORT", "EQ:NOFAC", "EQ:NAN", "EQ:NEW"), A)
    out = _run(names, _forward(*names), betas)
    assert dict(out["outcome_reason"]) == {
        "EQ:SHORT": SHORT_HISTORY, "EQ:NOFAC": NO_FACTOR_HISTORY, "EQ:NAN": NO_BETAS,
        "EQ:NEW": NO_BETAS,
    }  # fmt: skip
    assert out["fwd_residual_return"].isna().all()


def test_no_betas_partition_at_all_is_no_betas() -> None:
    out = _run({"EQ:A": A}, _forward("EQ:A"), None)
    assert out.loc["EQ:A", "outcome_reason"] == NO_BETAS
    assert out.loc["EQ:A", "outcome_status"] == "UNMEASURED"


def test_a_factor_etf_gap_at_the_window_end_is_no_factor_bar() -> None:
    rows = [
        {"instrument_id": i, "session_date": d, "close": 1.0 + k * 0.01}
        for i in ("E:SPY", "E:IWM", "E:MTUM", "E:VLUE", "EQ:A")
        for k, d in enumerate(WINDOW.sessions)
        if not (i == "E:IWM" and k == 4)
    ]
    closes = wide_closes(pd.DataFrame(rows), WINDOW, "close")
    out = residual_rows(_forward("EQ:A"), closes, WINDOW, ETF, _betas({"EQ:A": {}}), BEFORE)
    assert out.set_index("instrument_id").loc["EQ:A", "outcome_reason"] == NO_FACTOR_BAR


def test_a_sector_loading_whose_etf_has_no_bar_is_unmeasured() -> None:
    sector = {"EQ:A": {"beta_sector": 0.4, "factor_status": "OK", "sector_etf": "XLF"}}
    out = _run({"EQ:A": A}, _forward("EQ:A"), _betas(sector))
    assert out.loc["EQ:A", "outcome_reason"] == NO_FACTOR_BAR  # XLF is not in the reference


def test_an_unmeasured_forward_row_is_carried_with_its_reason() -> None:
    forward = pd.DataFrame(
        {"instrument_id": ["EQ:A", "EQ:BAD"], "fwd_return": [0.3, np.nan],
         "outcome_status": ["COMPLETE", "UNMEASURED"], "outcome_reason": [None, "BAD_BAR"]}
    )  # fmt: skip
    out = _run({"EQ:A": A, "EQ:BAD": A}, forward, _betas({"EQ:A": {}, "EQ:BAD": {}}))
    assert out.loc["EQ:BAD", "outcome_reason"] == "BAD_BAR"
    assert pd.isna(out.loc["EQ:BAD", "fwd_residual_return"])
    assert out.loc["EQ:A", "outcome_status"] == "COMPLETE"


def test_zero_loadings_leave_the_return_untouched() -> None:
    zero = dict.fromkeys(BETAS, 0.0)
    out = _run({"EQ:A": A}, _forward("EQ:A"), _betas({"EQ:A": zero}))
    assert out.loc["EQ:A", "fwd_residual_return"] == pytest.approx(0.30)
    assert out.loc["EQ:A", "fwd_factor_return"] == pytest.approx(0.0)
