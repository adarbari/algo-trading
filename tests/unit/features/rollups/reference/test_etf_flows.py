"""``etf_flows@v1``: an iShares fund's share count and its change over 21 sessions; null (never
zero) without a count from a month earlier, with a stale latest count or a non-positive one."""

from datetime import date, timedelta

import pandas as pd
import pytest

from algotrade.core.time.calendar import sessions_ending
from algotrade.features.rollups.reference import etf_flows
from algotrade.features.rollups.reference.etf_flows import SHARES, compute

SESSION = date(2026, 11, 20)
BACK = sessions_ending(SESSION, 22)[0]  # 21 sessions before the session
FUND, OTHER = "EQ:IVV", "EQ:IWM"


def _rows(items: list[tuple[str, date, float, date | None]]) -> pd.DataFrame:
    """``(fund, issuer date, shares, known_from)``; known_from defaults to the next day."""
    return pd.DataFrame(
        [
            {"instrument_id": i, "as_of": d, "shares_outstanding": s,
             "known_from": k or d + timedelta(days=1), "source": "ishares",
             "knowledge_ts": pd.Timestamp(k or d + timedelta(days=1), tz="UTC")}
            for i, d, s, k in items
        ]
    )  # fmt: skip


def _row(frame: pd.DataFrame, fund: str = FUND) -> pd.Series:
    return compute({SHARES: frame}, SESSION, None).set_index("instrument_id").loc[fund]


def test_the_change_is_the_latest_count_over_the_count_21_sessions_back() -> None:
    latest = SESSION - timedelta(days=1)
    row = _row(_rows([(FUND, BACK, 100.0, None), (FUND, latest, 110.0, None)]))
    assert row["etf_shares_chg_21d"] == pytest.approx(0.10)
    assert (
        row["etf_shares_outstanding"] == pytest.approx(110.0) and row["etf_shares_asof"] == latest
    )


def test_a_redemption_is_negative_and_the_base_may_sit_a_few_days_early() -> None:
    latest = SESSION - timedelta(days=1)
    row = _row(_rows([(FUND, BACK - timedelta(days=4), 200.0, None), (FUND, latest, 150.0, None)]))
    assert row["etf_shares_chg_21d"] == pytest.approx(-0.25)


def test_no_count_from_a_month_earlier_is_null_never_zero() -> None:
    latest = SESSION - timedelta(days=1)
    row = _row(
        _rows([(FUND, latest, 110.0, None), (FUND, latest - timedelta(days=3), 109.0, None)])
    )
    assert pd.isna(row["etf_shares_chg_21d"]) and row["etf_shares_outstanding"] == 110.0
    early = _row(
        _rows([(FUND, BACK - timedelta(days=9), 100.0, None), (FUND, latest, 110.0, None)])
    )
    assert pd.isna(early["etf_shares_chg_21d"])  # the base is more than 7 days before the span


def test_a_stale_latest_count_has_no_change_and_a_much_older_one_no_row() -> None:
    stale = SESSION - timedelta(days=10)
    frame = _rows([(FUND, BACK, 100.0, None), (FUND, stale, 110.0, None),
                   (OTHER, SESSION - timedelta(days=45), 5.0, None)])  # fmt: skip
    out = compute({SHARES: frame}, SESSION, None).set_index("instrument_id")
    assert pd.isna(out.loc[FUND, "etf_shares_chg_21d"]) and OTHER not in out.index


def test_a_restated_count_replaces_the_original_for_the_same_issuer_date() -> None:
    latest = SESSION - timedelta(days=1)
    frame = _rows([(FUND, BACK, 100.0, None), (FUND, latest, 110.0, None),
                   (FUND, latest, 120.0, SESSION)])  # fmt: skip
    assert _row(frame)["etf_shares_chg_21d"] == pytest.approx(0.20)


def test_a_non_positive_count_is_dropped_and_no_input_is_an_empty_frame() -> None:
    latest = SESSION - timedelta(days=1)
    assert pd.isna(_row(_rows([(FUND, BACK, 0.0, None), (FUND, latest, 110.0, None)]))[
        "etf_shares_chg_21d"])  # fmt: skip
    assert compute({SHARES: None}, SESSION, None).empty
    assert list(compute({SHARES: _rows([])}, SESSION, None).columns) == [
        "instrument_id",
        *etf_flows.COLUMNS,
    ]
