"""``analyst_estimates@v1``: FY1 and FY2 from our own FMP snapshots, the fiscal-year roll, annual
estimates only, STALE after 21 days, NOT_COVERED and NOT_FETCHED told apart, the personal
licence."""

from datetime import date

import pandas as pd
import pytest

from algotrade.features.framework.columns import conform
from algotrade.features.rollups.consensus import analyst_estimates as ae
from algotrade.features.rollups.consensus.analyst_status import (
    NOT_COVERED,
    NOT_FETCHED,
    OK,
    STALE,
    UNCOVERED,
)
from tests.helpers.analyst_snapshots import estimates, marker, night, put, store, universe, visible

A, B, C = "EQ:A", "EQ:B", "EQ:C"
S = date(2026, 10, 16)
YEARS = {"2025-12-31": 4.0, "2026-12-31": 5.0, "2027-12-31": 6.0, "2028-12-31": 7.0}


def run(writer, session: date = S, ids=(A,), financials=None, p=None) -> pd.DataFrame:
    inputs = {
        ae.SNAPSHOTS: visible(writer, session),
        ae.UNIVERSE: universe(*ids),
        ae.FINANCIALS: financials,
    }
    return ae.compute(inputs, session, p or ae.EstimatesParams()).set_index("instrument_id")


def fy_end(iid: str, end: str) -> pd.DataFrame:
    return pd.DataFrame({"instrument_id": [iid], "revenue_fy_end": [pd.Timestamp(end)]})


def snapshot_of(session: date, *rows: dict, writer=None):
    writer = writer or store()
    put(writer, session, [r for group in rows for r in group])
    return writer


def test_fy1_is_the_first_year_after_the_last_annual_report_and_rolls_with_the_10k() -> None:
    """A December filer: until its 10-K for 2025 is known, FY1 is the unreported 2025 and FY2
    2026; the day it is known FY1 becomes 2026. The vendor's list is the same on both days."""
    writer = snapshot_of(date(2026, 2, 6), estimates(A, YEARS))
    before = run(writer, date(2026, 2, 10), financials=fy_end(A, "2024-12-31")).loc[A]
    after = run(writer, date(2026, 2, 10), financials=fy_end(A, "2025-12-31")).loc[A]
    assert (before["fy1_period_end"], before["fy2_period_end"]) == (
        date(2025, 12, 31),
        date(2026, 12, 31),
    )
    assert (before["eps_fy1"], before["eps_fy2"]) == (4.0, 5.0)
    assert (after["fy1_period_end"], after["fy2_period_end"]) == (
        date(2026, 12, 31),
        date(2027, 12, 31),
    )
    assert (after["eps_fy1"], after["eps_fy2"]) == (5.0, 6.0)
    assert after["revenue_fy1"] == 5.0e9 and after["eps_fy1_analysts"] == 12
    assert after["revenue_fy1_analysts"] == 9 and after[ae._STATUS] == OK


def test_without_a_known_annual_report_fy1_is_the_first_year_ending_after_the_session() -> None:
    writer = snapshot_of(S, estimates(A, YEARS))
    row = run(writer, S, financials=None).loc[A]
    assert row["fy1_period_end"] == date(2026, 12, 31) and row["eps_fy1"] == 5.0
    other = run(
        writer, S, financials=pd.DataFrame({"instrument_id": [B], "revenue_fy_end": [None]})
    ).loc[A]
    assert other["fy1_period_end"] == date(2026, 12, 31)  # a frame with no end for the name


def test_a_52_week_year_end_the_vendor_dates_a_few_days_apart_is_still_that_report() -> None:
    """The filing says the year ended 2025-09-27, the vendor lists 2025-09-30: that is the
    reported year, so FY1 is 2026-09-30. Fails without the ``fy_slack_days`` tolerance."""
    writer = snapshot_of(S, estimates(A, {"2025-09-30": 3.0, "2026-09-30": 4.0, "2027-09-30": 5.0}))
    row = run(writer, S, financials=fy_end(A, "2025-09-27")).loc[A]
    assert (row["fy1_period_end"], row["eps_fy1"]) == (date(2026, 9, 30), 4.0)
    strict = run(
        writer, S, financials=fy_end(A, "2025-09-27"), p=ae.EstimatesParams(fy_slack_days=0)
    ).loc[A]
    assert strict["fy1_period_end"] == date(2025, 9, 30)


def test_only_annual_estimates_count_and_only_the_newest_snapshot_is_read() -> None:
    older = date(2026, 10, 9)
    writer = snapshot_of(older, estimates(A, {"2026-12-31": 1.0, "2027-12-31": 2.0}))
    put(
        writer,
        S,
        [
            *estimates(A, {"2027-12-31": 3.0, "2028-12-31": 4.0}),
            {"instrument_id": A, "kind": "grades", "period": "current", "eps_avg": 99.0},
            {"instrument_id": A, "kind": "price_target", "period": "current", "eps_avg": 98.0},
        ],
    )
    row = run(writer, S).loc[A]
    # the newest fetch no longer lists 2026: the older fetch's 2026 is not mixed in
    assert (row["fy1_period_end"], row["fy2_period_end"]) == (
        date(2027, 12, 31),
        date(2028, 12, 31),
    )
    assert (row["eps_fy1"], row["eps_fy2"]) == (3.0, 4.0)
    assert row["estimates_age_days"] == 0


def test_a_snapshot_older_than_21_days_is_stale_and_serves_no_values() -> None:
    writer = snapshot_of(date(2026, 9, 25), estimates(A, YEARS))
    edge = run(writer, date(2026, 10, 16)).loc[A]  # 21 days: still OK
    assert (edge[ae._STATUS], edge["estimates_age_days"], edge["eps_fy1"]) == (OK, 21, 5.0)
    stale = run(writer, date(2026, 10, 17)).loc[A]  # 22 days
    assert stale[ae._STATUS] == STALE and stale["estimates_age_days"] == 22
    assert pd.isna(stale["eps_fy1"]) and pd.isna(stale["fy1_period_end"])
    assert pd.isna(stale["revenue_fy2"]) and pd.isna(stale["eps_fy1_analysts"])


def test_not_covered_and_not_fetched_are_told_apart() -> None:
    names = ("EQ:OK", "EQ:REFUSED", "EQ:NEVER", "EQ:FAILED", "EQ:EMPTY", "EQ:LATER")
    writer = store()
    put(writer, date(2026, 10, 9), estimates("EQ:LATER", YEARS))
    put(
        writer,
        S,
        [
            *estimates("EQ:OK", YEARS),
            marker("EQ:OK", "OK"),
            marker("EQ:REFUSED", "NOT_COVERED"),
            marker("EQ:FAILED", "FAILED"),
            marker("EQ:EMPTY", "EMPTY"),
            marker("EQ:LATER", "NOT_COVERED"),  # refused since its last data
        ],
    )
    got = run(writer, S, ids=names)
    assert got[ae._STATUS].to_dict() == {
        "EQ:OK": OK,
        "EQ:REFUSED": NOT_COVERED,
        "EQ:NEVER": NOT_FETCHED,  # no row, no marker: never asked
        "EQ:FAILED": NOT_FETCHED,  # an error says nothing about coverage
        "EQ:EMPTY": NOT_COVERED,
        "EQ:LATER": NOT_COVERED,
    }
    assert (
        got.loc[["EQ:REFUSED", "EQ:NEVER", "EQ:LATER"], ["eps_fy1", "estimates_age_days"]]
        .isna()
        .all()
        .all()
    )


def test_a_store_without_markers_reads_every_name_as_never_asked_or_ok() -> None:
    writer = snapshot_of(S, estimates(A, YEARS))
    got = run(writer, S, ids=(A, B))
    assert got[ae._STATUS].to_dict() == {A: OK, B: NOT_FETCHED}
    nothing = ae.compute(
        {ae.SNAPSHOTS: None, ae.UNIVERSE: universe(A, B), ae.FINANCIALS: None},
        S,
        ae.EstimatesParams(),
    )
    assert set(nothing[ae._STATUS]) == {NOT_FETCHED} and nothing["eps_fy1"].isna().all()


def test_one_row_per_equity_of_the_universe_whatever_the_snapshots_hold() -> None:
    writer = snapshot_of(S, estimates(A, YEARS), estimates("EQ:SPY", YEARS))
    inputs = {
        ae.SNAPSHOTS: visible(writer, S),
        ae.UNIVERSE: universe(A, B, etfs=("EQ:SPY",)),
        ae.FINANCIALS: None,
    }
    got = ae.compute(inputs, S, ae.EstimatesParams())
    assert sorted(got["instrument_id"]) == [A, B]  # the ETF is no equity, B was never asked


def test_a_late_rerun_does_not_reach_back_to_the_session_before_it() -> None:
    """End to end through the input: a Friday-morning re-run of Wednesday's night is not what
    Wednesday's rollup reads (the name then reads never asked); Friday's reads it."""
    wed, fri = date(2026, 10, 14), date(2026, 10, 16)
    writer = store()
    put(writer, wed, estimates(A, {"2026-12-31": 5.0}), "first")
    put(writer, wed, estimates(A, {"2026-12-31": 50.0}), "rerun", knowledge=night(fri, 14))
    assert run(writer, wed).loc[A, ae._STATUS] == NOT_FETCHED
    assert run(writer, fri).loc[A, "eps_fy1"] == 50.0


def test_the_output_conforms_to_the_declared_types_and_every_feature_is_personal() -> None:
    writer = snapshot_of(S, estimates(A, YEARS))
    conform("t", run(writer, S, ids=(A, B)).reset_index(), ae.COLUMNS)
    assert all(f.licence == "personal" for f in ae.GROUP.features)
    assert ae.GROUP.optional
    values = [f for f in ae.GROUP.features if f.name != ae._STATUS]
    assert all(f.null_status == ae._STATUS and f.uncovered_statuses == UNCOVERED for f in values)


@pytest.mark.parametrize("bad", [{"stale_days": 0}, {"fy_slack_days": -1}, {"fy_slack_days": 300}])
def test_params_are_validated(bad: dict) -> None:
    with pytest.raises(ValueError):
        ae.EstimatesParams(**bad)
