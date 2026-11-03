"""``peer_sensitivity@v1``: a peer is kept when its reports have moved the name, not because it is
alike; the name's own report days are skipped; windows end at the session; short history is null."""

from datetime import date, timedelta

import numpy as np
import pandas as pd

from algotrade.core.time.calendar import sessions_ending
from algotrade.features.rollups.corporate import earnings
from algotrade.features.rollups.event_study import event_reaction as er
from algotrade.features.rollups.event_study import peer_sensitivity as ps
from tests.helpers.stored_frames import stamped

SESSION = date(2026, 10, 2)
GRID = sessions_ending(SESSION, er.HISTORY + 1)
X, P, Q, SPY, YOUNG = "EQ:X", "EQ:P", "EQ:Q", "EQ:SPY", "EQ:YOUNG"
P_REPORTS = [GRID[-i] for i in range(70, 700, 70)]
Q_REPORTS = [GRID[-i - 10] for i in range(70, 700, 70)]
SPIKE = 0.08


def _bars() -> pd.DataFrame:
    rng = np.random.default_rng(3)
    common = rng.normal(0, 0.01, len(GRID))  # X, P and Q share it: they correlate
    rets = {n: common + rng.normal(0, 0.004, len(GRID)) for n in (X, P, Q)}
    rets[SPY] = rng.normal(0, 0.01, len(GRID))
    for d in P_REPORTS:  # X moves on P's report days (pre-market: P's own session)
        rets[X][GRID.index(d)] = -SPIKE
    rows = []
    for name, r in rets.items():
        close = 100 * np.exp(np.cumsum(r))
        rows += [
            {"instrument_id": name, "session_date": d, "close": c, "volume": 1000.0}
            for d, c in zip(GRID, close, strict=True)
        ]
    rows += [
        {"instrument_id": YOUNG, "session_date": d, "close": 10.0 + i % 3, "volume": 1.0}
        for i, d in enumerate(GRID[-50:])
    ]
    frame = pd.DataFrame(rows)
    for column in ("open", "high", "low"):
        frame[column] = frame["close"]
    return frame


def _report(iid: str, day: date) -> dict[str, object]:
    return {"instrument_id": iid, "ts": pd.Timestamp(day, tz="UTC"), "time": "pre_market",
            "known_from": day, "reported": True}  # fmt: skip


def _run(extra: list[dict[str, object]] | None = None) -> pd.DataFrame:
    rows = [_report(P, d) for d in P_REPORTS] + [_report(Q, d) for d in Q_REPORTS]
    rows += [_report(X, GRID[-5])] + (extra or [])
    symbols = pd.DataFrame({"instrument_id": [SPY], "symbol": ["SPY"]})
    inputs = {earnings.EVENTS: stamped(rows, SESSION, "e"), "bars/1d": _bars(),
              "instruments/symbol_ids": symbols, ps.COMPANY: None}  # fmt: skip
    return ps.compute(inputs, SESSION, None).set_index("instrument_id")


def test_a_peer_that_moved_the_name_on_its_reports_is_kept_and_one_that_did_not_is_not() -> None:
    row = _run().loc[X]
    assert row["peers_kept"] == 1 and row["peer_1_id"] == P
    assert row["peer_1_multiple"] > 4 and row["peer_1_n"] == 9
    assert pd.isna(row["peer_2_id"])  # Q correlates but its reports never moved X


def test_the_names_own_report_days_are_skipped() -> None:
    own = _run([_report(X, P_REPORTS[0])]).loc[X]  # X reports on one of P's days: that event is X's
    assert own["peer_1_id"] == P and own["peer_1_n"] == 8


def test_a_peer_with_too_few_reports_cannot_be_kept() -> None:
    rows = [_report(P, d) for d in P_REPORTS[:5]]  # five reports: under MIN_REPORTS
    symbols = pd.DataFrame({"instrument_id": [SPY], "symbol": ["SPY"]})
    inputs = {earnings.EVENTS: stamped(rows, SESSION, "e"), "bars/1d": _bars(),
              "instruments/symbol_ids": symbols, ps.COMPANY: None}  # fmt: skip
    out = ps.compute(inputs, SESSION, None).set_index("instrument_id")
    assert out.loc[X, "peers_kept"] == 0 and pd.isna(out.loc[X, "peer_1_id"])


def test_a_report_after_the_session_is_not_a_reaction_and_is_the_next_peer_report() -> None:
    future = {**_report(P, SESSION + timedelta(days=10)), "known_from": GRID[0], "reported": False}
    row = _run([future]).loc[X]
    assert row["peer_1_n"] == 9  # the future report is not tested
    assert row["next_peer_report_date"] == SESSION + timedelta(days=10)
    assert row["next_peer_report_id"] == P


def test_short_history_is_null_and_says_so() -> None:
    young = _run().loc[YOUNG]
    assert young["peer_status"] == ps.SHORT_HISTORY
    assert young.drop("peer_status").isna().all()
    assert _run().loc[X, "peer_status"] == ps.OK


def test_the_columns_are_declared_in_order() -> None:
    out = ps.compute(
        {earnings.EVENTS: stamped([_report(P, P_REPORTS[0])], SESSION, "e"), "bars/1d": _bars(),
         "instruments/symbol_ids": None, ps.COMPANY: None}, SESSION, None)  # fmt: skip
    assert list(out.columns) == ["instrument_id", *ps.COLUMNS]


def test_a_name_with_under_250_sessions_is_short_even_with_a_beta() -> None:
    out = _run()
    assert out.loc[YOUNG, "peer_status"] == ps.SHORT_HISTORY  # 50 sessions of bars
    assert out.loc[X, "candidates_tested"] >= 1  # P was judged


def test_without_spy_every_name_is_no_market_not_short_history() -> None:
    rows = [_report(P, d) for d in P_REPORTS]
    inputs = {earnings.EVENTS: stamped(rows, SESSION, "e"), "bars/1d": _bars(),
              "instruments/symbol_ids": None, ps.COMPANY: None}  # fmt: skip
    out = ps.compute(inputs, SESSION, None)
    assert set(out["peer_status"]) == {ps.NO_MARKET}


def test_standardised_treats_an_all_missing_column_as_zero_without_a_warning() -> None:
    """A name with no returns at all (a new listing) is zeros and not ok: the nightly runs pytest
    with warnings as errors, and a numpy empty-slice warning once failed the whole rollups step."""
    returns = np.full((ps.WINDOW, 2), np.nan)
    returns[:, 1] = np.linspace(-0.01, 0.01, ps.WINDOW)
    z, ok = ps.standardised(returns)
    assert not z[:, 0].any() and list(ok) == [False, True]
