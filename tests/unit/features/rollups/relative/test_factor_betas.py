"""``factor_betas@v1`` on hand-built bars: SPY, IWM, MTUM, VLUE and a sector ETF with known
random returns, and stocks built from them. The five loadings and the residual volatility are
recovered by the regression; a window the ETFs do not cover (MTUM / VLUE start in 2013), a
missing factor ETF, no sector or a short history is UNKNOWN with its status, never a
market-only fit; the window never reads past the session."""

from collections.abc import Mapping
from datetime import date

import numpy as np
import pandas as pd
import pytest

from algotrade.core.time.calendar import sessions_ending
from algotrade.data import StoreReader
from algotrade.features.framework.runner import compute_one
from algotrade.features.rollups.relative import factor_betas as fb
from tests.helpers.rollup_store import END, store, write_bars, write_rows
from tests.helpers.stored_frames import write_reference

GROUP = fb.GROUP
N = fb.WINDOW + 1  # 253 closes
DAYS = sessions_ending(END, N)
rng = np.random.default_rng(11)
RETURNS = {t: rng.normal(0.0003, 0.01, N - 1) for t in ("SPY", "IWM", "MTUM", "VLUE", "XLK", "XLV")}
NOISE = 0.001


def path(daily: np.ndarray, base: float = 100.0) -> np.ndarray:
    """``N`` closes compounding the daily LOG returns (so the regression is exact in logs)."""
    return base * np.exp(np.concatenate([[0.0], np.cumsum(daily)]))


def loaded(
    mkt: float, size: float, mom: float, val: float, sec: float, sector: str = "XLK"
) -> np.ndarray:
    """Daily log returns with these loadings on the five factors, plus noise of ``NOISE``."""
    spy = RETURNS["SPY"]
    daily = (
        mkt * spy
        + size * (RETURNS["IWM"] - spy)
        + mom * (RETURNS["MTUM"] - spy)
        + val * (RETURNS["VLUE"] - spy)
        + sec * (RETURNS[sector] - spy)
    )
    return daily + np.random.default_rng(5).normal(0.0, NOISE, N - 1)


CLOSES = {f"EQ:{t}": path(r) for t, r in RETURNS.items()}
CLOSES |= {
    "EQ:A": path(loaded(1.3, 0.4, -0.2, 0.6, 0.5)),
    "EQ:B": path(loaded(0.6, -0.3, 0.1, 0.0, 0.8, "XLV")),
    "EQ:N": path(loaded(1.0, 0.0, 0.0, 0.0, 0.0)),  # no sector
    "EQ:M": path(loaded(1.2, 0.4, -0.2, 0.6, 0.0)),  # no sector, no sector loading: four factors
}
SECTORS = {"EQ:A": "XLK", "EQ:B": "XLV", "EQ:N": None, "EQ:M": None}


def build(
    closes: Mapping[str, np.ndarray] = CLOSES,
    sectors: Mapping[str, str | None] | None = SECTORS,
    *,
    upto: int = N - 1,
    skip: Mapping[str, list[int]] | None = None,
) -> StoreReader:
    writer, reader = store()
    write_bars(writer, {i: c[: upto + 1] for i, c in closes.items()}, end=DAYS[upto], skip=skip)
    write_reference(writer, DAYS[0], {i[3:]: i for i in closes})
    if sectors is not None:
        for day in DAYS[max(0, upto - 9) : upto + 1]:  # the sector map of each of the last sessions
            rows = pd.DataFrame(
                {"instrument_id": list(sectors), "sector_etf": list(sectors.values())}
            )
            rows["session_date"] = day
            write_rows(
                writer, "rollups/instrument/relative_strength@v1", day, rows.to_dict("records")
            )
    return reader


def result(reader: StoreReader, session: date = END) -> dict[str, dict[str, object]]:
    frame = compute_one(reader, GROUP, session, None).frame
    assert frame is not None
    return frame.set_index("instrument_id").to_dict("index")


def null(value: object) -> bool:
    return bool(pd.isna(value))


def test_the_four_loadings_and_the_residual_volatility_are_recovered_without_a_sector() -> None:
    m = result(build())["EQ:M"]
    assert m["factor_status"] == fb.NO_SECTOR and m["factor_obs"] == fb.WINDOW
    for column, truth in zip(fb.BETAS[:4], (1.2, 0.4, -0.2, 0.6), strict=True):
        assert float(m[column]) == pytest.approx(truth, abs=0.1), column  # type: ignore[arg-type]
    assert null(m["beta_sector"])
    # the noise is what the factors leave: NOISE a day, annualised
    assert float(m[fb.IVOL]) == pytest.approx(NOISE * np.sqrt(fb.ANNUAL), rel=0.12)  # type: ignore[arg-type]


def test_beta_sector_comes_from_the_five_factor_fit_of_the_names_own_sector_etf() -> None:
    out = result(build())
    assert out["EQ:A"]["factor_status"] == fb.OK
    assert float(out["EQ:A"]["beta_sector"]) == pytest.approx(0.5, abs=0.1)  # type: ignore[arg-type]
    assert float(out["EQ:B"]["beta_sector"]) == pytest.approx(0.8, abs=0.1)  # type: ignore[arg-type]
    assert float(out["EQ:A"][fb.IVOL]) > 0


def test_a_history_with_no_sector_map_still_yields_ivol_and_the_four_betas() -> None:
    """Before the first company snapshot every sector_etf is null: only beta_sector is unknown."""
    out = result(build(sectors=dict.fromkeys(SECTORS)))
    for iid in ("EQ:A", "EQ:B", "EQ:N", "EQ:M"):
        row = out[iid]
        assert row["factor_status"] == fb.NO_SECTOR and null(row["beta_sector"]), iid
        assert not null(row["beta_mkt"]) and not null(row[fb.IVOL]), iid


def test_an_instrument_with_no_sector_is_no_sector_with_the_rest_set() -> None:
    n = result(build())["EQ:N"]
    assert n["factor_status"] == fb.NO_SECTOR and null(n["beta_sector"])
    assert float(n["beta_mkt"]) == pytest.approx(1.0, abs=0.1)  # type: ignore[arg-type]
    assert n["factor_obs"] == fb.WINDOW


def test_a_window_before_the_factor_etfs_exist_is_unknown_with_the_reason() -> None:
    """MTUM starts late: its returns are missing for the first part of the window, so no
    instrument gets a market-only fit; the window of every stock reads NO_FACTOR_HISTORY."""
    skip = {"EQ:MTUM": list(range(0, 100))}  # 100 sessions without a bar
    out = result(build(skip=skip))
    assert out["EQ:A"]["factor_status"] == fb.NO_FACTOR_HISTORY
    assert all(null(out["EQ:A"][c]) for c in (*fb.BETAS, fb.IVOL))


def test_a_missing_factor_etf_is_unknown_for_every_instrument() -> None:
    closes = {k: v for k, v in CLOSES.items() if k != "EQ:VLUE"}
    out = result(build(closes))
    assert {r["factor_status"] for r in out.values()} == {fb.NO_FACTOR_HISTORY}


def test_a_sector_etf_without_history_leaves_only_beta_sector_unknown() -> None:
    out = result(build(skip={"EQ:XLK": list(range(0, 100))}))
    assert out["EQ:A"]["factor_status"] == fb.NO_SECTOR and null(out["EQ:A"]["beta_sector"])
    assert not null(out["EQ:A"]["beta_mkt"])
    assert out["EQ:B"]["factor_status"] == fb.OK  # the other sector is unaffected


def test_a_short_listing_is_unknown_with_short_history() -> None:
    closes = dict(CLOSES)
    closes["EQ:A"] = CLOSES["EQ:A"][-120:]  # listed 120 sessions ago
    a = result(build(closes))["EQ:A"]
    assert a["factor_status"] == fb.SHORT_HISTORY and null(a["beta_mkt"]) and null(a[fb.IVOL])
    assert a["factor_obs"] == 119


def test_a_gap_costs_one_observation_not_the_window() -> None:
    a = result(build(skip={"EQ:M": [50]}))["EQ:M"]
    assert a["factor_status"] == fb.NO_SECTOR
    assert a["factor_obs"] == fb.WINDOW - 2  # the two returns that touch the missing bar
    assert float(a["beta_mkt"]) == pytest.approx(1.2, abs=0.1)  # type: ignore[arg-type]


def test_the_window_never_reads_past_the_session() -> None:
    """The row of an earlier session is the same whether or not later bars are stored."""
    early = DAYS[N - 6]
    full = result(build(), early)
    cut = result(build(upto=N - 6), early)
    assert full["EQ:A"]["beta_mkt"] == cut["EQ:A"]["beta_mkt"]
