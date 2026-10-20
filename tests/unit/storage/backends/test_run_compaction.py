"""The compaction planner and its verification (ADR 0078), on Arrow tables with no store."""

from datetime import timedelta

import pandas as pd
import pyarrow as pa
import pytest

from algotrade.storage.backends.run_compaction import (
    CompactionVerificationError,
    plan_compaction,
    verify_plan,
)
from algotrade.storage.backends.run_selection import RunEntry
from tests.helpers.stored_frames import T0

TABLE = "events/dividend"
TS = pd.Timestamp("2026-10-02", tz="UTC")


def run(k: int, rows: dict[str, float | None], **extra: list[object]) -> pa.Table:
    n = len(rows)
    data: dict[str, list[object]] = {
        "instrument_id": list(rows),
        "ts": [TS] * n,
        "cash_amount": list(rows.values()),
        "knowledge_ts": [pd.Timestamp(T0 + timedelta(hours=k))] * n,
        "run_id": [f"r{k}"] * n,
        **extra,
    }
    return pa.table(data)


def entry(k: int, restates: bool = False, seq: int | None = None) -> RunEntry:
    known = pd.Timestamp(T0 + timedelta(hours=k))
    return RunEntry(known, restates, known + pd.Timedelta(days=1), seq if seq else k, None)


def plan(runs: dict[str, pa.Table], entries: dict[str, RunEntry] | None = None):  # type: ignore[no-untyped-def]
    entries = entries or {r: entry(int(r[1:])) for r in runs}
    return plan_compaction(TABLE, entries, lambda r, _e: runs[r])


def test_an_identical_rewrite_is_dropped_and_the_last_run_is_kept_empty() -> None:
    result = plan({"r1": run(1, {"A": 1.0, "B": 2.0}), "r2": run(2, {"A": 1.0, "B": 2.0})})
    assert list(result.kept) == ["r1", "r2"] and result.kept["r2"].num_rows == 0
    assert result.kept["r2"].schema == run(2, {"A": 1.0}).schema and result.dropped == ()
    middle = plan({f"r{k}": run(k, {"A": 1.0}) for k in (1, 2, 3)})
    assert list(middle.kept) == ["r1", "r3"] and middle.dropped == ("r2",)


def test_a_revision_keeps_only_the_changed_rows_and_a_new_key_is_kept() -> None:
    result = plan(
        {
            "r1": run(1, {"A": 1.0, "B": 1.0}),
            "r2": run(2, {"A": 1.0, "B": 2.0, "C": 3.0}),
            "r3": run(3, {"B": 2.0}),
        }
    )
    assert result.kept["r2"].column("instrument_id").to_pylist() == ["B", "C"]
    assert result.rewritten == ("r2", "r3") and result.kept["r3"].num_rows == 0


def test_a_run_that_adds_or_loses_a_column_is_kept() -> None:
    added = plan({"r1": run(1, {"A": 1.0}), "r2": run(2, {"A": 1.0}, note=["x"])})
    assert added.kept["r2"].column("note").to_pylist() == ["x"]
    lost = plan(
        {"r1": run(1, {"A": 1.0}, note=["x"]), "r2": run(2, {"A": 1.0}), "r3": run(3, {"A": 1.0})}
    )
    assert lost.kept["r2"].column("instrument_id").to_pylist() == ["A"]  # note went null
    assert lost.dropped == ()


def test_a_column_only_a_dropped_run_had_keeps_its_run() -> None:
    result = plan(
        {
            "r1": run(1, {"A": 1.0}),
            "r2": run(2, {"A": 1.0}, note=[None]),
            "r3": run(3, {"A": 1.0}, note=[None]),
        }
    )
    assert list(result.kept) == ["r1", "r2", "r3"] and result.kept["r2"].num_rows == 0


def test_nan_equals_nan() -> None:
    nan = float("nan")
    result = plan({f"r{k}": run(k, {"A": nan}) for k in (1, 2, 3)})
    assert result.dropped == ("r2",)


def test_a_restating_run_or_a_mismatched_order_skips_the_partition() -> None:
    runs = {"r1": run(1, {"A": 1.0}), "r2": run(2, {"A": 1.0})}
    restating = plan(runs, {"r1": entry(1), "r2": entry(2, restates=True)})
    assert restating.skipped and not restating.kept
    late = RunEntry(pd.Timestamp(T0), False, pd.Timestamp(T0) + pd.Timedelta(days=3), 1)
    mismatch = plan(runs, {"r1": late, "r2": entry(2)})  # known first, visible last
    assert mismatch.skipped and "order" in mismatch.skipped


def test_a_snapshot_table_is_skipped() -> None:
    skipped = plan_compaction(
        "instruments/reference", {"r1": entry(1), "r2": entry(2)}, lambda *_: run(1, {"A": 1.0})
    )
    assert skipped.skipped


def test_a_plan_with_nothing_to_drop_is_a_no_op() -> None:
    assert plan({"r1": run(1, {"A": 1.0}), "r2": run(2, {"A": 2.0})}).noop is True


def test_verification_catches_a_wrong_value_and_a_row_not_in_the_source() -> None:
    runs = {"r1": run(1, {"A": 1.0}), "r2": run(2, {"A": 2.0})}
    entries = {r: entry(int(r[1:])) for r in runs}
    good = plan(runs, entries)
    verify_plan(TABLE, entries, runs, entries, good.kept)
    wrong = {"r1": runs["r1"], "r2": run(2, {"A": 9.0})}
    with pytest.raises(CompactionVerificationError, match="not in its source"):
        verify_plan(TABLE, entries, runs, entries, wrong)
    lost = {"r1": runs["r1"], "r2": runs["r2"].slice(0, 0)}
    with pytest.raises(CompactionVerificationError, match="values differ"):
        verify_plan(TABLE, entries, runs, entries, lost)
