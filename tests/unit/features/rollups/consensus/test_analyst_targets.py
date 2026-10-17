"""``analyst_targets@v1``: the price-target consensus of our own FMP snapshots, STALE after 21
days, the shared statuses, the personal licence."""

from datetime import date

import pandas as pd
import pytest

from algotrade.features.framework.columns import conform
from algotrade.features.rollups.consensus import analyst_targets as at
from algotrade.features.rollups.consensus.analyst_status import (
    NOT_COVERED,
    NOT_FETCHED,
    OK,
    STALE,
    UNCOVERED,
    AnalystParams,
)
from tests.helpers.analyst_snapshots import estimates, marker, put, store, target, universe, visible

A, B, C = "EQ:A", "EQ:B", "EQ:C"
S = date(2026, 10, 16)


def run(writer, session: date = S, ids=(A,)) -> pd.DataFrame:
    inputs = {at.SNAPSHOTS: visible(writer, session), at.UNIVERSE: universe(*ids)}
    return at.compute(inputs, session, AnalystParams()).set_index("instrument_id")


def test_the_targets_of_the_newest_snapshot_are_served_with_their_age() -> None:
    writer = store()
    put(writer, date(2026, 10, 9), [target(A, 100.0)])
    put(writer, date(2026, 10, 13), [target(A, 120.0)])
    row = run(writer).loc[A]
    assert (row["target_consensus"], row["target_median"]) == (120.0, 119.0)
    assert (row["target_high"], row["target_low"]) == (140.0, 100.0)
    assert (row["targets_age_days"], row["targets_status"]) == (3, OK)


def test_targets_older_than_21_days_are_stale_and_serve_no_values() -> None:
    writer = store()
    put(writer, date(2026, 9, 25), [target(A, 100.0)])
    assert run(writer, date(2026, 10, 16)).loc[A, "target_consensus"] == 100.0  # 21 days
    stale = run(writer, date(2026, 10, 17)).loc[A]  # 22 days
    assert stale["targets_status"] == STALE and stale["targets_age_days"] == 22
    assert stale[["target_consensus", "target_median", "target_high", "target_low"]].isna().all()


def test_not_covered_and_not_fetched_read_from_the_markers_and_other_kinds_do_not_count() -> None:
    writer = store()
    put(writer, S, [*estimates(A, {"2026-12-31": 5.0}), target(B, 50.0), marker(C, "NOT_COVERED")])
    got = run(writer, ids=(A, B, C, "EQ:D"))
    # A has estimates but no target row: its estimates are not targets; no marker: never asked
    assert got["targets_status"].to_dict() == {
        A: NOT_FETCHED,
        B: OK,
        C: NOT_COVERED,
        "EQ:D": NOT_FETCHED,
    }


def test_an_ok_marker_without_a_target_row_is_the_vendor_having_none() -> None:
    writer = store()
    put(writer, S, [marker(A, "OK")])
    assert run(writer).loc[A, "targets_status"] == NOT_COVERED


def test_a_store_without_the_table_reads_every_name_as_never_asked() -> None:
    got = at.compute({at.SNAPSHOTS: None, at.UNIVERSE: universe(A, B)}, S, AnalystParams())
    assert set(got["targets_status"]) == {NOT_FETCHED} and got["target_consensus"].isna().all()


def test_the_output_conforms_and_every_feature_is_personal_and_optional() -> None:
    writer = store()
    put(writer, S, [target(A, 100.0)])
    conform("t", run(writer, ids=(A, B)).reset_index(), at.COLUMNS)
    assert all(f.licence == "personal" for f in at.GROUP.features) and at.GROUP.optional
    values = [f for f in at.GROUP.features if f.name != "targets_status"]
    assert all(f.null_status == "targets_status" for f in values)
    assert all(f.uncovered_statuses == UNCOVERED for f in values)


def test_stale_days_must_be_positive() -> None:
    with pytest.raises(ValueError, match="stale_days"):
        AnalystParams(stale_days=0)
