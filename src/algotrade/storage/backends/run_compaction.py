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
the result before a backend swaps it in (``Commits.swap_runs`` locally).
"""

import math
from collections import Counter
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from itertools import pairwise

import pandas as pd
import pyarrow as pa

from algotrade.storage.backends.arrow import concat, table_spec
from algotrade.storage.backends.run_selection import (
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


class CompactionVerificationError(RuntimeError):
    """The compacted partition does not read as the original at some cut: nothing was swapped."""


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


def _digest(data: pa.Table | None, names: list[str]) -> list[int]:
    return [] if data is None else sorted(hash(repr(row)) for row in _rows(data, names))


def verify_plan(
    table: str,
    entries: Mapping[str, RunEntry],
    sources: Mapping[str, pa.Table],
    kept_entries: Mapping[str, RunEntry],
    kept_tables: Mapping[str, pa.Table],
) -> None:
    """Raise ``CompactionVerificationError`` unless the kept runs read, at every ``visible_from``,
    one microsecond before it and with no ``as_of``, as the original runs do: same key set and
    row count and the same sorted hash of every column but the stamps; each row stamped at or
    before the cut; and every kept row exists unchanged in its source run."""
    for run, kept in kept_tables.items():
        source = sources[run]
        extra = Counter(_rows(kept, kept.column_names)) - Counter(_rows(source, kept.column_names))
        if kept.column_names != source.column_names or extra:
            raise CompactionVerificationError(f"run {run}: a kept row is not in its source")
    cuts: list[pd.Timestamp | None] = [None]
    for entry in entries.values():
        cuts += [entry.visible_from, entry.visible_from - pd.Timedelta(microseconds=1)]
    views = [(entries, kept_entries, cut) for cut in cuts]
    for upto in sorted({e.seq for e in entries.values() if e.seq is not None}):
        old_seen = visible_entries(entries, upto)
        if any(old_seen[r] is not entries[r] for r in old_seen):
            continue  # an older version of a run is involved: its rows are not loaded here
        try:
            views.append((old_seen, visible_entries(kept_entries, upto), None))
        except StaleSnapshotError:
            continue  # the read retries at a fresh sequence: it never mixes
    for old_entries, new_entries, cut in views:
        old = _merged(table, select_runs(old_entries, cut, "merge"), sources)
        new = _merged(table, select_runs(new_entries, cut, "merge"), kept_tables)
        old_cols = [] if old is None else old.column_names
        new_cols = [] if new is None else new.column_names
        if set(old_cols) != set(new_cols):
            raise CompactionVerificationError(f"columns differ at {cut}")
        names = sorted(c for c in old_cols if c not in STAMPS)
        if (0 if old is None else old.num_rows) != (0 if new is None else new.num_rows) or (
            _digest(old, names) != _digest(new, names)
        ):
            raise CompactionVerificationError(f"values differ at {cut}")
        if cut is not None and new is not None and "knowledge_ts" in new.column_names:
            stamped = [pd.Timestamp(v) for v in new.column("knowledge_ts").to_pylist() if v]
            if stamped and max(stamped) > cut:
                raise CompactionVerificationError(f"a row is stamped after the cut {cut}")
