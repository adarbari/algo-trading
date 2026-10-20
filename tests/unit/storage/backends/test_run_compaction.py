"""The compaction planner and its verification (ADR 0078), on Arrow tables with no store."""

import time
from collections import Counter
from datetime import timedelta

import numpy as np
import pandas as pd
import pyarrow as pa
import pytest

from algotrade.storage.backends import run_compaction as rc
from algotrade.storage.backends.run_compaction import (
    Budget,
    CompactionOverBudgetError,
    CompactionVerificationError,
    plan_compaction,
    verify_plan,
)
from algotrade.storage.backends.run_selection import RunEntry, select_runs
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


# --- the vectorised verifier against the slow reference it replaced (ADR 0078 follow-up) ---------


def _slow_reference(entries, sources, kept_entries, kept_tables) -> bool:  # type: ignore[no-untyped-def]
    """The per-row Python verifier of the first version, kept as the oracle: whether it accepts."""

    def rows(data, names):  # type: ignore[no-untyped-def]
        return rc._rows(data, names)

    def digest(data, names):  # type: ignore[no-untyped-def]
        return [] if data is None else sorted(hash(repr(r)) for r in rows(data, names))

    for r, kept in kept_tables.items():
        extra = Counter(rows(kept, kept.column_names)) - Counter(
            rows(sources[r], kept.column_names)
        )
        if kept.column_names != sources[r].column_names or extra:
            return False
    cuts = [None]
    for e in entries.values():
        cuts += [e.visible_from, e.visible_from - pd.Timedelta(microseconds=1)]
    for cut in cuts:
        old = rc._merged(TABLE, select_runs(entries, cut, "merge"), sources)
        new = rc._merged(TABLE, select_runs(kept_entries, cut, "merge"), kept_tables)
        old_cols = [] if old is None else old.column_names
        new_cols = [] if new is None else new.column_names
        if set(old_cols) != set(new_cols):
            return False
        names = sorted(c for c in old_cols if c not in rc.STAMPS)
        if (0 if old is None else old.num_rows) != (0 if new is None else new.num_rows):
            return False
        if digest(old, names) != digest(new, names):
            return False
        if cut is not None and new is not None:
            stamped = [pd.Timestamp(v) for v in new.column("knowledge_ts").to_pylist() if v]
            if stamped and max(stamped) > cut:
                return False
    return True


def _accepts(entries, sources, kept_tables) -> bool:  # type: ignore[no-untyped-def]
    try:
        verify_plan(TABLE, entries, sources, entries, kept_tables)
    except CompactionVerificationError:
        return False
    return True


def _scenarios():  # type: ignore[no-untyped-def]
    nan = float("nan")
    runs = {
        "r1": run(1, {"A": 1.0, "B": nan, "C": None}),
        "r2": run(2, {"A": 1.0, "B": nan, "C": 5.0}),
        "r3": run(3, {"A": 2.0, "B": nan}),
    }
    entries = {r: entry(int(r[1:])) for r in runs}
    good = plan(runs, entries).kept
    swap = lambda r, t: {**good, r: t}  # noqa: E731
    late = pd.Timestamp(T0 + timedelta(days=30))
    stamped_late = {
        "r1": run(1, {"A": 1.0}).set_column(3, "knowledge_ts", pa.array([late] * 1)),
        "r2": run(2, {"A": 3.0}),
    }
    dup = run(1, {"A": 1.0, "B": 2.0})
    dup = pa.concat_tables([dup, dup.slice(0, 1)])
    return {
        "good": (entries, runs, good),
        "changed value": (entries, runs, swap("r2", run(2, {"C": 9.0}))),
        "extra row": (entries, runs, swap("r3", run(3, {"A": 2.0, "Z": 1.0}))),
        "missing row": (entries, runs, swap("r2", runs["r2"].slice(0, 0))),
        "nan versus null": (entries, runs, swap("r1", run(1, {"A": 1.0, "B": None, "C": None}))),
        "null versus nan": (
            entries,
            {**runs, "r1": run(1, {"A": 1.0, "B": None, "C": None})},
            swap("r1", run(1, {"A": 1.0, "B": nan, "C": None})),
        ),
        "column dropped": (entries, runs, swap("r1", runs["r1"].drop_columns(["cash_amount"]))),
        "column added": (
            entries,
            runs,
            swap("r1", runs["r1"].append_column("note", pa.array(["x"] * 3))),
        ),
        "stamp after the cut": (
            {r: entry(int(r[1:])) for r in stamped_late},
            stamped_late,
            stamped_late,
        ),
        "duplicate row only in the kept run": (
            {"r1": entry(1)},
            {"r1": run(1, {"A": 1.0, "B": 2.0})},
            {"r1": dup},
        ),
        "duplicate row only in the source": (
            {"r1": entry(1)},
            {"r1": dup},
            {"r1": run(1, {"A": 1.0, "B": 2.0})},
        ),
    }


@pytest.mark.parametrize("name", list(_scenarios()))
def test_the_vectorised_verifier_agrees_with_the_per_row_reference(name: str) -> None:
    entries, sources, kept = _scenarios()[name]
    assert _accepts(entries, sources, kept) == _slow_reference(entries, sources, entries, kept)


def test_the_scenarios_cover_both_outcomes() -> None:
    verdicts = {n: _accepts(e, s, k) for n, (e, s, k) in _scenarios().items()}
    assert verdicts["good"] and not any(v for n, v in verdicts.items() if n != "good")


def test_a_list_column_is_compared_by_value() -> None:
    def with_list(k: int, values: list[list[float]]) -> pa.Table:
        return run(k, {"A": 1.0}).append_column("curve", pa.array(values, pa.list_(pa.float64())))

    runs = {"r1": with_list(1, [[1.0, float("nan")]]), "r2": with_list(2, [[2.0]])}
    entries = {r: entry(int(r[1:])) for r in runs}
    assert _accepts(entries, runs, runs)
    changed = {"r1": runs["r1"], "r2": with_list(2, [[3.0]])}
    assert not _accepts(entries, runs, changed)


def test_verification_compares_each_distinct_selection_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:

    runs = {f"r{k}": run(k, {"A": float(k)}) for k in range(1, 9)}
    entries = {r: entry(int(r[1:])) for r in runs}
    calls: list[int] = []
    original = rc._merged
    monkeypatch.setattr(rc, "_merged", lambda *a: calls.append(1) or original(*a))
    verify_plan(TABLE, entries, runs, entries, runs)
    assert len(calls) == 2 * (len(runs) + 1)  # a prefix of 0..8 runs, old and kept: not 2 x cuts


def test_a_spent_budget_stops_verification_cleanly() -> None:
    runs = {"r1": run(1, {"A": 1.0}), "r2": run(2, {"A": 2.0})}
    entries = {r: entry(int(r[1:])) for r in runs}
    with pytest.raises(CompactionOverBudgetError, match="over budget"):
        verify_plan(TABLE, entries, runs, entries, runs, Budget(0))
    verify_plan(TABLE, entries, runs, entries, runs, Budget(3600))
    with pytest.raises(CompactionOverBudgetError):
        plan_compaction(TABLE, entries, lambda r, _e: runs[r], Budget(0))


def test_a_budget_counts_from_its_creation_on_the_given_clock() -> None:
    now = [0.0]
    budget = Budget(10, lambda: now[0])
    budget.check()
    now[0] = 9.9
    budget.check()
    now[0] = 10.0
    with pytest.raises(CompactionOverBudgetError):
        budget.check()
    Budget(None).check()


def test_verifying_twenty_runs_of_a_hundred_thousand_rows_takes_seconds() -> None:
    """The regression of the first version: per-row Python hashing took minutes on a live
    partition of 20 runs. The bound is generous (several times the measured time)."""
    rows, runs_n = 100_000, 20
    ids = pa.array([f"EQ:{i}" for i in range(rows)])
    ts = pa.array([TS] * rows)
    sources = {}
    for k in range(1, runs_n + 1):
        amount = np.arange(rows, dtype="float64")
        amount[:10] = k  # ten rows revised by every run
        sources[f"r{k}"] = pa.table(
            {
                "instrument_id": ids,
                "ts": ts,
                "cash_amount": amount,
                "knowledge_ts": pa.array([pd.Timestamp(T0 + timedelta(hours=k))] * rows),
                "run_id": [f"r{k}"] * rows,
            }
        )
    kept = {r: (t if r == "r1" else t.slice(0, 10)) for r, t in sources.items()}
    entries = {r: entry(int(r[1:])) for r in sources}
    started = time.monotonic()
    verify_plan(TABLE, entries, sources, entries, kept)
    assert time.monotonic() - started < 60
