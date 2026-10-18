"""``analyst_revisions@v1``: the change of the FY1 consensus against our own earlier snapshots of
the SAME fiscal year (matched on the year end, never the FY1 label), the MIN_BASE floor, OK /
BUILDING / NO_PRIOR, and no snapshot the session could not know."""

from datetime import date

import pandas as pd
import pytest

from algotrade.features.framework.columns import conform
from algotrade.features.rollups.consensus import analyst_estimates as ae
from algotrade.features.rollups.consensus import analyst_revisions as rv
from algotrade.features.rollups.consensus.earnings_surprise import MIN_BASE
from tests.helpers.analyst.snapshots import estimates, marker, night, put, store, universe, visible

A, B, C = "EQ:A", "EQ:B", "EQ:C"
S = date(2027, 1, 15)  # a Friday
D90, D60, D30 = date(2026, 10, 16), date(2026, 11, 13), date(2026, 12, 11)  # 91, 63, 35 days back
YEAR = "2026-12-31"  # FY1 of a December filer whose last annual report is for 2025
NEXT = "2027-12-31"
REVISIONS = [c for c in rv.COLUMNS if "_revision_" in c]


def fin(iid: str, fy_end: str = "2025-12-31") -> pd.DataFrame:
    return pd.DataFrame(
        {"instrument_id": [iid], "revenue_fy_end": [pd.Timestamp(fy_end)], "qtr_as_of": [pd.NaT]}
    )


def rollup(writer, session: date = S, ids=(A,), fy_end: str = "2025-12-31") -> pd.DataFrame:
    """``analyst_estimates@v1`` for the session as the store holds it (typed as stored)."""
    inputs = {
        ae.SNAPSHOTS: visible(writer, session),
        ae.UNIVERSE: universe(*ids),
        ae.FINANCIALS: pd.concat([fin(i, fy_end) for i in ids]),
    }
    return conform("t", ae.compute(inputs, session, ae.EstimatesParams()), ae.COLUMNS)


def run(writer, session: date = S, ids=(A,), fy_end: str = "2025-12-31") -> pd.DataFrame:
    inputs = {
        rv.ESTIMATES_TABLE: rollup(writer, session, ids, fy_end),
        rv.SNAPSHOTS: visible(writer, session),
    }
    return rv.compute(inputs, session, None).set_index("instrument_id")


def years(eps: float, **more) -> list[dict]:
    return estimates(A, {YEAR: eps, NEXT: eps + 1}, **more)


def history(writer, *, now: float = 5.5) -> None:
    """Four snapshots of A: 90, 60 and 30 days back and tonight's; the EPS climbs."""
    put(writer, D90, years(4.0, num_analysts_eps=10))
    put(writer, D60, years(4.4))
    put(writer, D30, years(5.0))
    put(writer, S, years(now))


def test_the_revisions_compare_the_same_fiscal_year_with_each_earlier_snapshot() -> None:
    writer = store()
    history(writer)
    row = run(writer).loc[A]
    assert row["eps_fy1_revision_30d"] == pytest.approx(10.0)  # 5.0 -> 5.5
    assert row["eps_fy1_revision_60d"] == pytest.approx(25.0)  # 4.4 -> 5.5
    assert row["eps_fy1_revision_90d"] == pytest.approx(37.5)  # 4.0 -> 5.5
    assert row["revenue_fy1_revision_30d"] == pytest.approx(10.0)  # revenue is eps x 1e9 here
    assert row["revenue_fy1_revision_90d"] == pytest.approx(37.5)
    assert row["eps_fy1_analysts_change_90d"] == 2  # 12 now, 10 then
    assert row["revisions_status"] == rv.OK


def test_a_fiscal_year_roll_is_not_a_jump_it_compares_the_new_year_with_its_own_past() -> None:
    """The 10-K makes FY1 2027: the old snapshots listed 2027 as the second year at 5.0, which is
    the value the new FY1 moves from (not 2026's 4.0): +10%, not a change of year."""
    writer = store()
    put(writer, D90, estimates(A, {YEAR: 4.0, NEXT: 5.0}))
    put(writer, S, estimates(A, {YEAR: 4.2, NEXT: 5.5}))
    row = run(writer, fy_end="2026-12-31").loc[A]
    assert row["eps_fy1_revision_90d"] == pytest.approx(10.0)


def test_a_year_the_old_snapshots_did_not_list_has_no_revision() -> None:
    """Old snapshots list only the year that has since been reported: nothing matches the new
    FY1, so every revision is null (never the old FY1's value against the new one)."""
    writer = store()
    put(writer, D90, estimates(A, {YEAR: 4.0}))
    put(writer, S, estimates(A, {YEAR: 4.2, NEXT: 5.5}))
    row = run(writer, fy_end="2026-12-31").loc[A]
    assert row[REVISIONS].isna().all()
    assert row["revisions_status"] == rv.NO_PRIOR


def test_the_year_matches_on_its_end_within_ten_days_never_on_a_neighbouring_year() -> None:
    writer = store()
    put(writer, D90, estimates(A, {"2026-12-28": 4.0, "2027-12-26": 9.0}))  # a 52 week year
    put(writer, S, years(5.0))
    assert run(writer).loc[A, "eps_fy1_revision_90d"] == pytest.approx(25.0)
    other = store()
    put(other, D90, estimates(A, {"2026-12-15": 4.0}))  # 16 days off: another year
    put(other, S, years(5.0))
    assert pd.isna(run(other).loc[A, "eps_fy1_revision_90d"])


def test_a_base_below_the_floor_gives_no_percent_and_a_loss_counts_by_its_size() -> None:
    writer = store()
    put(writer, D90, estimates(A, {YEAR: MIN_BASE / 2}))
    put(writer, D60, estimates(A, {YEAR: 0.0}), run_id="z")
    put(writer, D30, estimates(A, {YEAR: -1.0}), run_id="n")
    put(writer, S, estimates(A, {YEAR: -0.8}))
    row = run(writer).loc[A]
    assert pd.isna(row["eps_fy1_revision_90d"]) and pd.isna(row["eps_fy1_revision_60d"])
    assert row["eps_fy1_revision_30d"] == pytest.approx(20.0)  # (-0.8 + 1.0) / |-1.0|
    assert (
        row["revisions_status"] == rv.OK
    )  # the status says snapshots exist, not that bases are fine


def test_building_has_some_history_and_no_prior_has_none_of_the_year() -> None:
    writer = store()
    put(writer, D30, [*years(5.0), *estimates(B, {"2025-12-31": 1.0})], run_id="a")
    put(
        writer, S, [*years(5.5), *estimates(B, {YEAR: 2.0}), *estimates(C, {YEAR: 3.0})], run_id="b"
    )
    got = run(writer, ids=(A, B, C))
    assert got["revisions_status"].to_dict() == {A: rv.BUILDING, B: rv.NO_PRIOR, C: rv.NO_PRIOR}
    assert got.loc[A, "eps_fy1_revision_30d"] == pytest.approx(10.0)
    assert pd.isna(got.loc[A, "eps_fy1_revision_90d"]) and pd.isna(
        got.loc[B, "eps_fy1_revision_30d"]
    )


def test_a_week_old_snapshot_alone_is_building_not_ok() -> None:
    writer = store()
    put(writer, date(2027, 1, 8), years(5.0))
    put(writer, S, years(5.5))
    row = run(writer).loc[A]
    assert row["revisions_status"] == rv.BUILDING and row[REVISIONS].isna().all()


def test_a_snapshot_older_than_the_window_and_its_slack_is_not_the_snapshot_then() -> None:
    writer = store()
    put(writer, date(2026, 10, 6), years(4.0))  # 101 days back: past 90 + 7
    put(writer, S, years(5.5))
    assert pd.isna(run(writer).loc[A, "eps_fy1_revision_90d"])


def test_the_latest_snapshot_of_the_window_is_the_one_compared() -> None:
    writer = store()
    put(writer, date(2026, 10, 12), years(1.0), run_id="early")
    put(writer, D90, years(4.0))
    put(writer, S, years(5.0))
    assert run(writer).loc[A, "eps_fy1_revision_90d"] == pytest.approx(25.0)


def test_a_snapshot_published_after_the_next_open_is_not_the_history_of_the_session() -> None:
    """The lookahead rule through the input: the 90-day snapshot is re-run late, after Tuesday's
    open, so Friday cannot know it and the 90-day revision is null; Tuesday can read it."""
    tue = date(2027, 1, 19)
    writer = store()
    put(writer, S, years(5.0))
    put(writer, D90, years(4.0), knowledge=night(tue, 15))
    friday = run(writer, S).loc[A]
    assert pd.isna(friday["eps_fy1_revision_90d"]) and friday["revisions_status"] == rv.NO_PRIOR
    assert run(writer, tue).loc[A, "eps_fy1_revision_90d"] == pytest.approx(25.0)


def test_a_snapshot_for_a_later_session_is_never_the_past() -> None:
    writer = store()
    put(writer, S, years(5.0))
    put(writer, date(2027, 1, 18), years(50.0))
    inputs = {
        rv.ESTIMATES_TABLE: rollup(writer, S),
        rv.SNAPSHOTS: visible(writer, date(2027, 1, 18)),
    }
    got = rv.compute(inputs, S, None).set_index("instrument_id")
    assert got.loc[A, "revisions_status"] == rv.NO_PRIOR


def test_only_names_with_served_estimates_have_a_row() -> None:
    writer = store()
    put(writer, S, [*years(5.0), marker(B, "NOT_COVERED")])
    put(writer, date(2026, 12, 1), estimates(C, {YEAR: 3.0}), run_id="old")  # 45 days: STALE
    got = run(writer, ids=(A, B, C, "EQ:D"))
    assert list(got.index) == [A]


def test_without_the_estimates_rollup_or_snapshots_there_is_nothing_to_compare() -> None:
    assert rv.compute({rv.ESTIMATES_TABLE: None, rv.SNAPSHOTS: None}, S, None).empty
    writer = store()
    put(writer, S, years(5.0))
    est = rollup(writer)
    got = rv.compute({rv.ESTIMATES_TABLE: est, rv.SNAPSHOTS: None}, S, None)
    assert got["revisions_status"].tolist() == [rv.NO_PRIOR]


def test_the_output_conforms_and_every_feature_is_personal_and_optional() -> None:
    writer = store()
    history(writer)
    conform("t", run(writer).reset_index(), rv.COLUMNS)
    conform("t", rv.compute({rv.ESTIMATES_TABLE: None, rv.SNAPSHOTS: None}, S, None), rv.COLUMNS)
    assert all(f.licence == "personal" for f in rv.GROUP.features) and rv.GROUP.optional
    assert rv.WINDOWS == (30, 60, 90) and not any("7d" in f.name for f in rv.GROUP.features)
    assert rv.GROUP.params is None
