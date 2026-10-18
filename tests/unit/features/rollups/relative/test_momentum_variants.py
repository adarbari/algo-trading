"""``momentum_variants@v1`` on hand-built bars: SPY, two sector ETFs and a few stocks. The
residual 12-1 and 1-month returns (beta from the same window; a stock that is exactly SPY has
none left), information discreteness (continuous against jumpy winners, a loser's sign),
the sector columns through ``relative_strength@v1``'s ``sector_etf``; a missing SPY, a gap, a
short history or no sector gives null, and the window never reads past the session."""

from collections.abc import Mapping
from datetime import date

import numpy as np
import pandas as pd
import pytest

from algotrade.core.time.calendar import sessions_ending
from algotrade.data import StoreReader
from algotrade.features.framework.runner import compute_one
from algotrade.features.rollups.relative import momentum_variants as mv
from tests.helpers.rollup_store import END, store, write_bars, write_rows
from tests.helpers.stored_frames import write_reference

GROUP = mv.GROUP
N = mv.LOOKBACK + 1  # 253 closes
DAYS = sessions_ending(END, N)
F32 = 2e-6


def path(daily: np.ndarray, base: float = 100.0) -> np.ndarray:
    """``N`` closes from ``base``, compounding the ``N - 1`` daily returns."""
    return base * np.concatenate([[1.0], np.cumprod(1.0 + daily)])


rng = np.random.default_rng(7)
SPY_RET = rng.normal(0.0004, 0.01, N - 1)
SPY = path(SPY_RET)
# B moves 1.5x SPY every day plus a constant drift: beta 1.5, residual log return from the drift
B = path(1.5 * SPY_RET + 0.0005)
# C: 12-1 window of steady small ups; D: the same total gain in a few big jumps
UP = np.full(N - 1, 0.0006)
JUMPY = np.zeros(N - 1)
JUMPY[::40] = 0.0006 * 40 * 1.02
CLOSES = {
    "EQ:SPY": SPY,
    "EQ:A": SPY.copy(),  # exactly the market: no residual
    "EQ:B": B,
    "EQ:C": path(UP),
    "EQ:D": path(JUMPY),
    "EQ:L": path(np.full(N - 1, -0.0005)),  # a loser: steady falls
    "EQ:XLK": path(np.full(N - 1, 0.0003)),
    "EQ:XLV": path(np.full(N - 1, -0.0002)),
}
SECTORS = {"EQ:A": "XLK", "EQ:B": "XLV", "EQ:C": None}


def build(
    closes: Mapping[str, np.ndarray] = CLOSES,
    sectors: Mapping[str, str | None] | None = SECTORS,
    *,
    skip: Mapping[str, list[int]] | None = None,
    upto: int = N - 1,
    with_symbols: bool = True,
) -> StoreReader:
    writer, reader = store()
    write_bars(writer, {i: c[: upto + 1] for i, c in closes.items()}, end=DAYS[upto], skip=skip)
    if with_symbols:
        write_reference(writer, DAYS[0], {i[3:]: i for i in closes})
    if sectors is not None:
        rows = pd.DataFrame({"instrument_id": list(sectors), "sector_etf": list(sectors.values())})
        rows["session_date"] = DAYS[upto]
        write_rows(
            writer, "rollups/instrument/relative_strength@v1", DAYS[upto], rows.to_dict("records")
        )
    return reader


def result(reader: StoreReader, session: date = END) -> dict[str, dict[str, object]]:
    frame = compute_one(reader, GROUP, session, None).frame
    assert frame is not None
    return frame.set_index("instrument_id").to_dict("index")


def null(value: object) -> bool:
    return bool(pd.isna(value))


def test_resid_mom_is_the_log_gain_less_beta_times_spys_over_the_12_1_window() -> None:
    out = result(build())

    # the 12-1 window: closes 252 to 21 sessions back = rows 0 .. N - 22
    def gain(c: np.ndarray) -> float:
        return float(np.log(c[N - 22] / c[0]))

    assert out["EQ:A"]["resid_mom_12_1"] == pytest.approx(0.0, abs=F32)  # is the market
    assert out["EQ:SPY"]["resid_mom_12_1"] == pytest.approx(0.0, abs=F32)
    # B's daily log return is ~1.5 x SPY's + drift, so its beta is near 1.5 and the residual is
    # its own gain less beta x SPY's, whatever beta the regression returns
    r = np.diff(np.log(B[: N - 21]))
    m = np.diff(np.log(SPY[: N - 21]))
    beta = np.cov(r, m, ddof=0)[0, 1] / m.var()
    assert out["EQ:B"]["resid_mom_12_1"] == pytest.approx(gain(B) - beta * gain(SPY), abs=1e-4)


def test_resid_ret_20d_uses_the_trailing_252_session_beta() -> None:
    out = result(build())
    r = np.diff(np.log(B))
    m = np.diff(np.log(SPY))
    beta = np.cov(r, m, ddof=0)[0, 1] / m.var()
    month = float(np.log(B[-1] / B[-21]) - beta * np.log(SPY[-1] / SPY[-21]))
    assert out["EQ:B"]["resid_ret_20d"] == pytest.approx(month, abs=1e-4)
    assert out["EQ:A"]["resid_ret_20d"] == pytest.approx(0.0, abs=F32)


def test_information_discreteness_is_negative_for_a_steady_winner_and_positive_for_jumps() -> None:
    out = result(build())
    # C rose every one of the 231 days: down share 0 - up share 1
    assert out["EQ:C"]["fip_12_1"] == pytest.approx(-1.0)
    # D: up on 6 of 231 days (every 40th, from the first), flat otherwise: down 0 - up 6/231,
    # a winner, so the sign is positive and the value small and negative: still fewer up days
    assert out["EQ:D"]["fip_12_1"] == pytest.approx(-6 / 231, rel=F32)
    # a loser's sign flips: down share 1 - up share 0 = 1, times sign -1
    assert out["EQ:L"]["fip_12_1"] == pytest.approx(-1.0)


def test_discreteness_separates_a_choppy_winner_from_a_smooth_one() -> None:
    choppy = np.where(np.arange(N - 1) % 2 == 0, 0.03, -0.0099)  # up and down, net up
    out = result(build({**CLOSES, "EQ:E": path(choppy)}))
    # half the days up, half down: the shares cancel
    assert out["EQ:E"]["fip_12_1"] == pytest.approx(0.0, abs=0.01)


def test_sector_columns_read_the_etf_through_relative_strengths_sector_etf() -> None:
    out = result(build())
    xlk, xlv = CLOSES["EQ:XLK"], CLOSES["EQ:XLV"]
    assert out["EQ:A"]["sector_ret_252d"] == pytest.approx(xlk[-1] / xlk[0] - 1, rel=F32)
    assert out["EQ:B"]["sector_ret_252d"] == pytest.approx(xlv[-1] / xlv[0] - 1, rel=F32)
    own = SPY[-1] / SPY[-21] - 1
    etf = xlk[-1] / xlk[-21] - 1
    assert out["EQ:A"]["rs_sector_20d"] == pytest.approx((1 + own) / (1 + etf) - 1, rel=1e-4)
    assert null(out["EQ:C"]["sector_ret_252d"]) and null(out["EQ:C"]["rs_sector_20d"])  # no sector


def test_unknowns_are_null_never_zero() -> None:
    no_spy = {k: v for k, v in CLOSES.items() if k != "EQ:SPY"}
    out = result(build(no_spy))
    assert null(out["EQ:B"]["resid_mom_12_1"]) and null(out["EQ:B"]["resid_ret_20d"])
    assert not null(out["EQ:C"]["fip_12_1"])  # discreteness needs no market
    assert null(result(build(with_symbols=False))["EQ:B"]["resid_mom_12_1"])
    assert null(result(build(sectors=None))["EQ:A"]["sector_ret_252d"])
    # a gap inside the 12-1 window nulls the 12-1 columns but not the 1-month one
    gap = result(build(skip={"EQ:B": [N - 100]}))["EQ:B"]
    assert null(gap["resid_mom_12_1"]) and null(gap["fip_12_1"])
    assert not null(gap["resid_ret_20d"])


def test_a_gap_in_the_last_month_nulls_the_month_columns_and_not_the_12_1() -> None:
    out = result(build(skip={"EQ:B": [N - 5]}))["EQ:B"]
    assert null(out["resid_ret_20d"]) and null(out["rs_sector_20d"])
    assert not null(out["resid_mom_12_1"])


def test_a_later_bar_is_never_read() -> None:
    # the session before the last sees the same 12-1 columns as a store that ends there
    full = build()
    earlier = DAYS[N - 2]
    short = build(upto=N - 2)
    a = result(full, earlier)
    b = result(short, earlier)
    for iid in ("EQ:B", "EQ:C"):
        assert a[iid]["fip_12_1"] == b[iid]["fip_12_1"] or (
            null(a[iid]["fip_12_1"]) and null(b[iid]["fip_12_1"])
        )
