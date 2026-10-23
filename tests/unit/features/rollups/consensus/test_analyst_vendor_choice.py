"""One vendor per (name, kind) in the estimates, targets and revisions groups (ADR 0080): FMP's
when its status is OK or STALE, else Yahoo's when it has a row or a marker that is not FAILED,
else FMP's; the loser's rows and markers dropped; no name judged by another; revisions only
against the chosen vendor's own history."""

from datetime import date

import pandas as pd
import pytest

from algotrade.features.framework.columns import conform
from algotrade.features.rollups.consensus import analyst_estimates as ae
from algotrade.features.rollups.consensus import analyst_revisions as rv
from algotrade.features.rollups.consensus import analyst_targets as at
from algotrade.features.rollups.consensus.analyst_status import (
    NOT_COVERED,
    NOT_FETCHED,
    OK,
    STALE,
    AnalystParams,
)
from tests.helpers.analyst.snapshots import estimates, marker, put, store, target, universe, visible

A, B, C = "EQ:A", "EQ:B", "EQ:C"
S = date(2026, 10, 22)
YEAR, NEXT = "2026-12-31", "2027-12-31"


def targets(writer, ids=(A,), session: date = S) -> pd.DataFrame:
    inputs = {at.SNAPSHOTS: visible(writer, session), at.UNIVERSE: universe(*ids)}
    return at.compute(inputs, session, AnalystParams()).set_index("instrument_id")


def fin(iid: str) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "instrument_id": [iid],
            "revenue_fy_end": [pd.Timestamp("2025-12-31")],
            "qtr_as_of": [pd.NaT],
        }
    )


def estimate_table(writer, ids=(A,), session: date = S) -> pd.DataFrame:
    inputs = {
        ae.SNAPSHOTS: visible(writer, session),
        ae.UNIVERSE: universe(*ids),
        ae.FINANCIALS: pd.concat([fin(i) for i in ids]),
    }
    return conform("t", ae.compute(inputs, session, ae.EstimatesParams()), ae.COLUMNS)


def revisions(writer, ids=(A,), session: date = S) -> pd.DataFrame:
    inputs = {
        rv.ESTIMATES_TABLE: estimate_table(writer, ids, session),
        rv.SNAPSHOTS: visible(writer, session),
    }
    return rv.compute(inputs, session, None).set_index("instrument_id")


def years(iid: str, eps: float) -> list[dict]:
    return estimates(iid, {YEAR: eps, NEXT: eps + 1})


def test_a_name_fmp_refuses_with_yahoo_rows_reads_values_not_not_covered() -> None:
    """The gap: FMP's marker says NOT_COVERED, Yahoo has the rows, and the group read only FMP."""
    writer = store()
    put(writer, S, [marker(A, "NOT_COVERED")])
    put(writer, S, [target(A, 20.0), *years(A, 0.9), marker(A, "OK")], run_id="y", source="yahoo")
    row = targets(writer).loc[A]
    assert (row["targets_status"], row["targets_source"], row["target_consensus"]) == (
        OK,
        "yahoo",
        20.0,
    )
    est = estimate_table(writer).set_index("instrument_id").loc[A]
    assert (est["estimates_status"], est["estimates_source"], est["eps_fy1"]) == (OK, "yahoo", 0.9)


def test_fmp_wins_when_it_is_ok_whatever_yahoo_has() -> None:
    writer = store()
    put(writer, S, [target(A, 100.0), marker(A, "OK")])
    put(writer, S, [target(A, 20.0), marker(A, "OK")], run_id="y", source="yahoo")
    row = targets(writer).loc[A]
    assert (row["targets_source"], row["target_consensus"]) == ("fmp", 100.0)


def test_fmp_wins_when_it_is_stale_and_serves_nothing_rather_than_yahoo() -> None:
    writer = store()
    put(writer, date(2026, 9, 1), [target(A, 100.0)])  # 51 days old: STALE
    put(writer, S, [target(A, 20.0)], run_id="y", source="yahoo")
    row = targets(writer).loc[A]
    assert (row["targets_status"], row["targets_source"]) == (STALE, "fmp")
    assert pd.isna(row["target_consensus"])


def test_the_vendor_is_chosen_per_kind() -> None:
    """FMP answers the targets but has no estimates for the name: estimates come from Yahoo."""
    writer = store()
    put(writer, S, [target(A, 100.0), marker(A, "OK")])
    put(writer, S, [*years(A, 0.9), marker(A, "OK")], run_id="y", source="yahoo")
    assert targets(writer).loc[A, "targets_source"] == "fmp"
    est = estimate_table(writer).set_index("instrument_id").loc[A]
    assert (est["estimates_source"], est["estimates_status"]) == ("yahoo", OK)


def test_the_losers_markers_never_mix_in() -> None:
    """FMP's newer NOT_COVERED marker must not turn Yahoo's rows into NOT_COVERED, and Yahoo's
    marker must not hide FMP's rows."""
    writer = store()
    put(writer, date(2026, 10, 20), [target(A, 20.0), marker(A, "OK")], run_id="y", source="yahoo")
    put(writer, S, [marker(A, "NOT_COVERED")])
    row = targets(writer).loc[A]
    assert (row["targets_status"], row["targets_source"], row["targets_age_days"]) == (
        OK,
        "yahoo",
        2,
    )
    other = store()
    put(other, date(2026, 10, 20), [target(A, 100.0), marker(A, "OK")])
    put(other, S, [marker(A, "NOT_COVERED")], run_id="y", source="yahoo")
    assert targets(other).loc[A, "targets_source"] == "fmp"


def test_a_name_yahoo_has_not_reached_stays_what_fmp_says_and_no_name_judges_another() -> None:
    writer = store()
    put(writer, S, [marker(A, "NOT_COVERED"), marker(B, "NOT_COVERED"), target(C, 50.0)])
    put(
        writer, S, [target(A, 20.0), marker(A, "OK")], run_id="y", source="yahoo"
    )  # Yahoo reached only A
    got = targets(writer, ids=(A, B, C))
    assert got["targets_status"].to_dict() == {A: OK, B: NOT_COVERED, C: OK}
    assert got["targets_source"].to_dict() == {A: "yahoo", B: "fmp", C: "fmp"}


def test_yahoo_failed_markers_say_nothing_and_leave_fmps_answer() -> None:
    writer = store()
    put(writer, S, [marker(A, "NOT_COVERED")])
    put(writer, S, [marker(A, "FAILED")], run_id="y", source="yahoo")
    row = targets(writer).loc[A]
    assert (row["targets_status"], row["targets_source"]) == (NOT_COVERED, "fmp")
    nothing = store()
    put(nothing, S, [marker(A, "FAILED")], run_id="y", source="yahoo")
    assert targets(nothing).loc[A, "targets_status"] == NOT_FETCHED


def test_yahoo_not_covered_is_chosen_over_an_fmp_that_never_asked() -> None:
    writer = store()
    put(writer, S, [marker(A, "NOT_COVERED")], run_id="y", source="yahoo")
    row = targets(writer).loc[A]
    assert (row["targets_status"], row["targets_source"]) == (NOT_COVERED, "yahoo")


def test_revisions_never_compare_across_a_vendor_flip() -> None:
    """FMP's history runs 90 and 60 days back, then FMP stops covering the name and Yahoo's
    snapshots begin 35 days back: the revision looks only at Yahoo's own, so the 60 and 90 day
    columns are null (the FMP snapshots exist but are another vendor's)."""
    writer = store()
    d90, d60, d35 = date(2026, 7, 24), date(2026, 8, 21), date(2026, 9, 17)
    put(writer, d90, years(A, 4.0))
    put(writer, d60, years(A, 4.4))
    put(writer, d35, [marker(A, "NOT_COVERED")])  # FMP lapses
    put(writer, d35, years(A, 5.0), run_id="y", source="yahoo")
    put(writer, S, years(A, 5.5), run_id="y", source="yahoo")
    row = revisions(writer).loc[A]
    assert row["revisions_source"] == "yahoo"
    assert row["eps_fy1_revision_30d"] == pytest.approx(10.0)  # Yahoo 5.0 -> 5.5
    assert pd.isna(row["eps_fy1_revision_60d"]) and pd.isna(row["eps_fy1_revision_90d"])
    assert row["revisions_status"] == rv.BUILDING


def test_revisions_of_an_fmp_name_ignore_yahoo_snapshots() -> None:
    writer = store()
    d30 = date(2026, 9, 21)
    put(writer, d30, years(A, 5.0))
    put(writer, d30, years(A, 99.0), run_id="y", source="yahoo")
    put(writer, S, years(A, 5.5))
    row = revisions(writer).loc[A]
    assert row["revisions_source"] == "fmp"
    assert row["eps_fy1_revision_30d"] == pytest.approx(10.0)  # against FMP's 5.0, not Yahoo's 99


def test_the_source_column_passes_through_uncovered_names() -> None:
    writer = store()
    put(writer, S, [marker(B, "NOT_COVERED")])
    out = revisions(writer, ids=(A, B))
    assert out.loc[B, "revisions_status"] == NOT_COVERED
    assert out["revisions_source"].to_dict() == {A: "fmp", B: "fmp"}


def test_every_column_of_the_three_groups_is_yahoo_licensed() -> None:
    for group in (ae.GROUP, at.GROUP, rv.GROUP):
        assert {f.licence for f in group.features} == {"yahoo"}, group.name
