"""Grading our values against IBKR's: tolerances, WARN / FAIL bands, NA, the dividend-gap
rule for the 52-week low, option mids within the spread band. Values from IBKR's recorded
2026-10-02 snapshot (the reconciliation suite's session) where it helps."""

from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from algotrade.config.site.settings import VerificationSettings
from algotrade.quant import realized_vol
from algotrade_ingestion.tasks.verification import checks

SESSION = date(2026, 10, 2)
S = VerificationSettings()
# IBKR, 2026-10-02 (recorded 2026-10-03): AAPL's last 21 closes, KO's 52-week range and yield.
AAPL_CLOSES = [
    325.13, 324.96, 328.21, 319.97, 316.22, 315.34, 326.57, 332.27, 333.08, 331.34, 332.41,
    337.0, 336.13, 338.98, 339.75, 337.02, 335.92, 341.07, 338.4, 329.4, 333.02,
]  # fmt: skip
KO_LOW_52W, KO_DIV_YIELD = 64.5145, 0.0244


def grader() -> checks.Grader:
    return checks.Grader("EQ:X", "X", S)


def bars(closes: list[float], end: date = SESSION) -> pd.DataFrame:
    days = [end - timedelta(len(closes) - 1 - i) for i in range(len(closes))]
    c = np.asarray(closes)
    return pd.DataFrame({"date": days, "high": c * 1.01, "low": c * 0.99, "close": c})


@pytest.mark.parametrize(
    ("diff", "status"), [(0.0, "PASS"), (0.002, "PASS"), (0.003, "WARN"), (0.005, "FAIL")]
)
def test_grade_bands(diff: float, status: str) -> None:
    assert checks.grade(diff, 0.002, 2.0) == status


def test_compare_is_na_when_a_side_is_missing() -> None:
    g = grader()
    g.compare("iv30", None, 0.25, 0.025, "abs")
    g.compare("iv30_cboe", 0.25, float("nan"), 0.025, "abs")
    assert [(r.status, r.note) for r in g.rows] == [
        ("NA", "no value (ours)"),
        ("NA", "no value (IBKR)"),
    ]


def test_bars_report_the_worst_session_and_missing_bars() -> None:
    theirs = bars(AAPL_CLOSES)
    ours = theirs.copy()
    ours.loc[5, "close"] *= 1.004  # one session off by 0.4%: FAIL (2 x 0.2% is the WARN band)
    ours = ours.drop(index=7)  # and one bar of ours missing
    g = grader()
    checks.compare_bars(g, ours, theirs, SESSION)
    by = {r.check: r for r in g.rows}
    assert by["close"].status == "FAIL" and str(theirs["date"][5]) in by["close"].note
    assert by["high"].status == "PASS" and by["low"].status == "PASS"
    assert by["bars_missing"].status == "WARN" and by["bars_missing"].diff == 1.0


def test_bars_na_when_ibkr_has_none() -> None:
    g = grader()
    checks.compare_bars(g, bars(AAPL_CLOSES), bars([])[:0], SESSION)
    assert {r.status for r in g.rows} == {"NA"}


def test_hv20_is_close_to_close_on_ibkr_closes() -> None:
    hv = float(realized_vol.close_to_close(np.asarray(AAPL_CLOSES), 20)[-1])
    assert checks.ibkr_hv20(np.asarray(AAPL_CLOSES)) == pytest.approx(hv)
    assert checks.ibkr_hv20(np.asarray(AAPL_CLOSES[:10])) is None
    year = bars([300.0] * 231 + AAPL_CLOSES)  # 252 sessions
    stats = pd.Series({"hv20": hv * 1.003, "high_52w": float(year["high"].max()),
                       "low_52w": float(year["low"].min())})  # fmt: skip
    g = grader()
    checks.compare_stats(g, stats, year, SESSION, div_ttm=None)
    assert {r.check: r.status for r in g.rows} == {
        "hv20": "PASS",
        "high_52w": "PASS",
        "low_52w": "PASS",
    }


def test_stats_na_without_our_row_a_session_bar_or_a_year_of_bars() -> None:
    g = grader()
    checks.compare_stats(g, None, bars(AAPL_CLOSES), SESSION, None)
    checks.compare_stats(g, pd.Series({"hv20": 0.2}), bars(AAPL_CLOSES, SESSION - timedelta(1)),
                         SESSION, None)  # fmt: skip
    checks.compare_stats(g, pd.Series({"hv20": 0.2}), bars(AAPL_CLOSES), SESSION, None)
    statuses = [(r.check, r.status) for r in g.rows]
    assert statuses[:6] == [(c, "NA") for c in ("hv20", "high_52w", "low_52w") * 2]
    assert statuses[-2:] == [("high_52w", "NA"), ("low_52w", "NA")]  # 21 sessions only


@pytest.mark.parametrize(
    ("ours", "div_ttm", "status"),
    [
        (KO_LOW_52W, None, "PASS"),  # same basis
        (65.35, 2.04, "PASS"),  # ours higher by less than the dividends: the dividend gap
        (67.0, 2.04, "FAIL"),  # higher by more than the dividends paid
        (64.0, 2.04, "FAIL"),  # ours below IBKR's: never explained by dividends
    ],
)
def test_low_52w_dividend_gap_rule(ours: float, div_ttm: float | None, status: str) -> None:
    g = grader()
    checks._low_52w(g, ours, KO_LOW_52W, div_ttm)
    assert g.rows[0].status == status
    g2 = grader()
    checks._low_52w(g2, None, KO_LOW_52W, div_ttm)
    assert g2.rows[0].status == "NA"


def test_dividend_yield_from_ib_trailing_twelve_months() -> None:
    close = 70.0
    ib = pd.DataFrame([{"past12Months": KO_DIV_YIELD * close, "close": close}])
    g = grader()
    checks.compare_yield(g, KO_DIV_YIELD + 0.0004, ib)
    checks.compare_yield(g, 0.0, pd.DataFrame([{"past12Months": None, "close": 10.0}]))
    checks.compare_yield(g, 0.01, None)
    assert [r.status for r in g.rows] == ["PASS", "PASS", "NA"]


def test_implied_vol_ours_and_cboe() -> None:
    iv = pd.DataFrame({"date": [SESSION], "close": [0.262622]})  # IBKR's AAPL IV
    g = grader()
    checks.compare_iv(g, pd.Series({"iv30": 0.25, "iv30_cboe": 0.20}), iv, SESSION)
    checks.compare_iv(g, None, iv.iloc[:0], SESSION)
    assert [(r.check, r.status) for r in g.rows] == [
        ("iv30", "PASS"),
        ("iv30_cboe", "FAIL"),
        ("iv30", "NA"),
        ("iv30_cboe", "NA"),
    ]


def test_option_mid_within_the_spread_band() -> None:
    ours = pd.Series({"right": "C", "strike": 230.0, "expiry": date(2026, 11, 20),
                      "bid": 5.0, "ask": 5.4})  # fmt: skip
    g = grader()
    checks.compare_option(g, ours, True, pd.DataFrame([{"bid": 5.1, "ask": 5.5}]))
    checks.compare_option(g, ours, False, pd.DataFrame([{"bid": 6.0, "ask": 6.4}]))
    checks.compare_option(g, ours, None, pd.DataFrame([{"bid": None, "ask": None}]))
    assert [(r.check, r.status) for r in g.rows] == [
        ("option_listed", "PASS"),
        ("option_mid", "PASS"),
        ("option_listed", "FAIL"),
        ("option_mid", "FAIL"),
        ("option_listed", "NA"),
        ("option_mid", "NA"),
    ]


def test_counts() -> None:
    g = grader()
    g.compare("a", 1.0, 1.0, 0.0, "abs")
    g.na("b", "x")
    assert checks.counts(g.rows) == {"PASS": 1, "WARN": 0, "FAIL": 0, "NA": 1}
    assert g.rows[0].as_dict()["check"] == "a"
