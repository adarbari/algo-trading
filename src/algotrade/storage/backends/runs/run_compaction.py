"""Value-exact compaction of one partition's runs: the plan and its verification (ADR 0078).

A merge-mode partition (``run_selection``) holds runs R1..Rn in selection order (``knowledge_ts``,
run id). A run that rewrote rows with identical values adds nothing to any read, yet its file
stays. Scheme E2 keeps run Rk only when it **adds a key, changes a column other than the stamps
(``knowledge_ts``, ``run_id``), or adds a column** against merge(R1..Rk-1), and then only those
rows (copied from the source, schema unchanged); Rn is always kept (possibly with no rows) so the
partition's highest commit sequence is unchanged. Every prefix of the kept runs then has the
values of the original prefix, so a read at any ``as_of`` or pinned at any ``upto`` returns the
same values; only a row's stamps can differ (earlier: when the value was first known).

The plan is pure: it takes the entries and a function reading a run's rows, and touches no store.
A partition the argument does not hold for is skipped with a reason: ``knowledge_ts`` order
differing from ``visible_from`` order (or commit order), or any restating run. ``verify`` checks
the result before a backend swaps it in (``Commits.swap_runs`` locally). Verification is
vectorised Arrow (a per-row Python hash of ~120 views took minutes on a 20-run partition) and
bounded by a ``Budget``.
"""

import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from itertools import pairwise
from time import monotonic

import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc

from algotrade.storage.backends.arrow import concat, table_spec
from algotrade.storage.backends.runs.run_selection import (
    RunEntry,
    StaleSnapshotError,
    merge_rows,
    run_mode,
    select_runs,
    visible_entries,
)
from algotrade.storage.tables.schemas import table_key

STAMPS = frozenset({"knowledge_ts", "run_id"})
_NAN = ("nan",)  # one value for every NaN, so two NaNs are equal
_LEFT, _RIGHT = "__left", "__right"  # row counts per side in a multiset comparison
OVER_BUDGET = "verification over budget"


class CompactionVerificationError(RuntimeError):
    """The compacted partition does not read as the original at some cut: nothing was swapped."""


class CompactionOverBudgetError(RuntimeError):
    """The partition's time budget was spent: nothing was swapped, the partition is skipped."""


class Budget:
    """A partition's time budget: ``check`` raises once ``seconds`` have passed since it began."""

    def __init__(self, seconds: float | None, clock: Callable[[], float] = monotonic) -> None:
        self.clock = clock
        self.end = None if seconds is None else clock() + seconds

    def check(self) -> None:
        if self.end is not None and self.clock() >= self.end:
            raise CompactionOverBudgetError(OVER_BUDGET)


@dataclass(frozen=True)
class CompactionPlan:
    """What to keep of a partition: each kept run's rows (oldest first), the runs dropped."""

    kept: dict[str, pa.Table] = field(default_factory=dict)
    dropped: tuple[str, ...] = ()
    rewritten: tuple[str, ...] = ()  # kept runs whose rows are fewer than their source's
    skipped: str | None = None

    @property
    def noop(self) -> bool:
        return self.skipped is None and not self.dropped and not self.rewritten


def _column(data: pa.Table, name: str) -> list[object]:
    if name not in data.column_names:
        return [None] * data.num_rows
    values = data.column(name).to_pylist()
    return [_NAN if isinstance(v, float) and math.isnan(v) else v for v in values]


def _rows(data: pa.Table, names: list[str]) -> list[tuple[object, ...]]:
    columns = [_column(data, n) for n in names]
    return list(zip(*columns, strict=True)) if names else [()] * data.num_rows


def _skip(reason: str) -> CompactionPlan:
    return CompactionPlan(skipped=reason)


def _order_problem(entries: Mapping[str, RunEntry], order: list[str]) -> str | None:
    if any(entries[r].restates for r in order):
        return "a run restates the partition"
    visible = [entries[r].visible_from for r in order]
    if any(a > b for a, b in pairwise(visible)):
        return "knowledge_ts order differs from visible_from order"
    seqs = [-1 if (seq := entries[r].seq) is None else seq for r in order]
    if any(a > b for a, b in pairwise(seqs)):
        return "knowledge_ts order differs from commit order"
    return None


def plan_compaction(
    table: str,
    entries: Mapping[str, RunEntry],
    read_run_table: Callable[[str, RunEntry], pa.Table],
    budget: Budget | None = None,
) -> CompactionPlan:
    """Scheme E2 over one partition's current entries (see the module docstring)."""
    spec = table_spec(table)
    if spec is None or run_mode(table) != "merge":
        return _skip("not a merge-mode table")
    order = sorted(entries, key=lambda r: (entries[r].knowledge_ts, r))
    if problem := _order_problem(entries, order):
        return _skip(problem)
    kept: dict[str, pa.Table] = {}
    dropped: list[str] = []
    rewritten: list[str] = []
    state: dict[tuple[object, ...], dict[str, object]] = {}  # key -> merged row (union columns)
    merged_columns: list[str] = []
    kept_columns: set[str] = set()
    for i, run in enumerate(order):
        if budget:
            budget.check()
        data = read_run_table(run, entries[run])
        names = [c for c in data.column_names if c not in STAMPS]
        key = table_key(spec, data.column_names)
        for c in names:
            if c not in merged_columns:
                merged_columns.append(c)
        rows = _rows(data, merged_columns)
        keys = _rows(data, key)
        index = {c: j for j, c in enumerate(merged_columns)}
        changed: list[int] = []
        for n, (k, row) in enumerate(zip(keys, rows, strict=True)):
            held = state.get(k)
            if held is None or any(held.get(c) != row[j] for c, j in index.items()):
                changed.append(n)
            state[k] = dict(zip(merged_columns, row, strict=True))
        new_columns = bool(set(data.column_names) - kept_columns)
        # a run with an older version stays: a read pinned before it must retry, not mix
        if not (changed or new_columns or i == len(order) - 1 or entries[run].prev is not None):
            dropped.append(run)
            continue
        kept[run] = data.take(pa.array(changed, pa.int64()))
        kept_columns |= set(data.column_names)
        if len(changed) < data.num_rows:
            rewritten.append(run)
    return CompactionPlan(kept, tuple(dropped), tuple(rewritten))


def kept_entries(
    entries: Mapping[str, RunEntry], plan: CompactionPlan, fresh: Mapping[str, str]
) -> dict[str, RunEntry]:
    """The index of the compacted partition: each kept run's entry as it was (``knowledge_ts``,
    ``visible_at``, ``seq`` and ``restates`` unchanged) with ``fresh[run]`` as the new reference of
    a rewritten run, and its older version forgotten (a read pinned before it retries)."""
    return {
        r: replace(
            entries[r],
            ref=fresh.get(r, entries[r].ref),
            prev=None,
            dropped=entries[r].dropped or entries[r].prev is not None,
        )
        for r in plan.kept
    }


def _merged(table: str, runs: list[str], tables: Mapping[str, pa.Table]) -> pa.Table | None:
    if not runs:
        return None
    data = concat(table, [tables[r] for r in runs])
    return merge_rows(table, data) if len(runs) > 1 else data


def _comparable(data: pa.Table | None, names: list[str], rows: int) -> pa.Table:
    """``names`` of ``data`` as groupable columns (a missing one is null; a list column, which
    Arrow cannot group on, becomes one string per row, NaNs as one value)."""
    columns: list[pa.ChunkedArray | pa.Array] = []
    for name in names:
        if data is None or name not in data.column_names:
            columns.append(pa.nulls(rows))
        elif pa.types.is_nested(data.schema.field(name).type):
            columns.append(pa.array([repr(v) for v in _column(data, name)], pa.string()))
        else:
            columns.append(data.column(name))
    return pa.table(columns, names=names)


def _multiset_gap(
    left: pa.Table | None, right: pa.Table | None, names: list[str], subset: bool
) -> bool:
    """Whether ``left`` is not equal (``subset`` False) or not contained (``subset`` True) as a
    multiset of rows over ``names``: null equals null and NaN equals NaN, any other value only
    itself. One vectorised group-by over both tables, no per-row Python."""
    n_left = 0 if left is None else left.num_rows
    n_right = 0 if right is None else right.num_rows
    if not names or not n_left or not n_right:
        return n_left > n_right if subset else n_left != n_right
    left_side, right_side = _comparable(left, names, n_left), _comparable(right, names, n_right)
    if left_side.schema.types != right_side.schema.types:
        return True  # a column that changed type (int64 -> float64) does not read as it did
    try:
        both = pa.concat_tables(
            [
                left_side.append_column(_LEFT, pa.array([1] * n_left)),
                right_side.append_column(_LEFT, pa.array([0] * n_right)),
            ],
            promote_options="none",
        )
        both = both.append_column(_RIGHT, pc.subtract(1, both.column(_LEFT)))
        sums = both.group_by(names, use_threads=False).aggregate([(_LEFT, "sum"), (_RIGHT, "sum")])
    except (pa.ArrowInvalid, pa.ArrowTypeError, pa.ArrowNotImplementedError) as exc:
        raise CompactionVerificationError(f"rows cannot be compared: {exc}") from exc
    a, b = sums.column(f"{_LEFT}_sum"), sums.column(f"{_RIGHT}_sum")
    return bool(pc.any(pc.greater(a, b) if subset else pc.not_equal(a, b)).as_py())


def _check_sources(
    kept_tables: Mapping[str, pa.Table], sources: Mapping[str, pa.Table], budget: Budget | None
) -> None:
    for run, kept in kept_tables.items():
        if budget:
            budget.check()
        source = sources[run]
        if kept.column_names != source.column_names or _multiset_gap(
            kept, source, kept.column_names, subset=True
        ):
            raise CompactionVerificationError(f"run {run}: a kept row is not in its source")


def _views(
    entries: Mapping[str, RunEntry], kept: Mapping[str, RunEntry]
) -> list[tuple[Mapping[str, RunEntry], Mapping[str, RunEntry], pd.Timestamp | None]]:
    cuts: list[pd.Timestamp | None] = [None]
    for entry in entries.values():
        cuts += [entry.visible_from, entry.visible_from - pd.Timedelta(microseconds=1)]
    views = [(entries, kept, cut) for cut in cuts]
    for upto in sorted({e.seq for e in entries.values() if e.seq is not None}):
        old_seen = visible_entries(entries, upto)
        if any(old_seen[r] is not entries[r] for r in old_seen):
            continue  # an older version of a run is involved: its rows are not loaded here
        try:
            views.append((old_seen, visible_entries(kept, upto), None))
        except StaleSnapshotError:
            continue  # the read retries at a fresh sequence: it never mixes
    return views


def verify_plan(
    table: str,
    entries: Mapping[str, RunEntry],
    sources: Mapping[str, pa.Table],
    kept_entries: Mapping[str, RunEntry],
    kept_tables: Mapping[str, pa.Table],
    budget: Budget | None = None,
) -> None:
    """Raise ``CompactionVerificationError`` unless the kept runs read, at every ``visible_from``,
    one microsecond before it, with no ``as_of`` and at every pinned sequence, as the original
    runs do: same columns, key set, row count and values of every column but the stamps (as
    multisets of rows); each row stamped at or before the cut; and every kept row exists
    unchanged in its source run. A view whose selected runs (old and kept) were already compared
    is not compared again (only its cut is added to the stamp check). ``budget`` raises
    ``CompactionOverBudgetError`` when spent."""
    try:
        _verify(table, entries, sources, kept_entries, kept_tables, budget)
    except (pa.ArrowInvalid, pa.ArrowTypeError, pa.ArrowNotImplementedError) as exc:
        raise CompactionVerificationError(f"rows cannot be compared: {exc}") from exc


def _verify(
    table: str,
    entries: Mapping[str, RunEntry],
    sources: Mapping[str, pa.Table],
    kept_entries: Mapping[str, RunEntry],
    kept_tables: Mapping[str, pa.Table],
    budget: Budget | None,
) -> None:
    _check_sources(kept_tables, sources, budget)
    seen: dict[tuple[tuple[str, ...], tuple[str, ...]], list[pd.Timestamp | None]] = {}
    for old_entries, new_entries, cut in _views(entries, kept_entries):
        if budget:
            budget.check()
        old_runs = tuple(select_runs(old_entries, cut, "merge"))
        new_runs = tuple(select_runs(new_entries, cut, "merge"))
        if (old_runs, new_runs) in seen:
            held = seen[old_runs, new_runs]
            if cut is not None and (held[1] is None or cut < held[1]):
                held[1] = cut
            continue
        old = _merged(table, list(old_runs), sources)
        new = _merged(table, list(new_runs), kept_tables)
        old_cols = [] if old is None else old.column_names
        new_cols = [] if new is None else new.column_names
        if set(old_cols) != set(new_cols):
            raise CompactionVerificationError(f"columns differ at {cut}")
        names = sorted(c for c in old_cols if c not in STAMPS)
        if _multiset_gap(old, new, names, subset=False):
            raise CompactionVerificationError(f"values differ at {cut}")
        newest = None
        if new is not None and "knowledge_ts" in new.column_names:
            top = pc.max(new.column("knowledge_ts")).as_py()
            newest = None if top is None else pd.Timestamp(top)
        seen[old_runs, new_runs] = [newest, cut]
    for newest, tightest in seen.values():
        if newest is not None and tightest is not None and newest > tightest:
            raise CompactionVerificationError(f"a row is stamped after the cut {tightest}")
