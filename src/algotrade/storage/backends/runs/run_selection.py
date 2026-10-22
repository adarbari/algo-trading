"""Point-in-time run selection shared by all backends, so they cannot disagree.

A partition (table, session_date) holds one or more runs, each indexed with its
``knowledge_ts`` and whether it **restates** the partition. Which runs a read at ``as_of``
sees depends on the table's run mode (``TableSpec.runs``, ``storage/tables/schemas.py``):

- ``snapshot``: the one run with the greatest ``knowledge_ts`` <= ``as_of`` (ties broken by
  run id). Each run is the partition's full contents.
- ``merge``: every run with ``knowledge_ts`` <= ``as_of``, from the latest **restating**
  run among them onwards (all of them when none restates), in (``knowledge_ts``, run id)
  order. Rows are unioned and the latest run's row wins per table key (``merge_rows``).
  A later run that no longer contains a row does not remove it (no tombstones yet,
  ADR 0007); a run that rewrites the whole partition (``migrate_ids``) is written as
  restating, so the rows it replaced (e.g. under old ids) stop being read after it.

Visibility (ADR 0022): a run written ``pending`` counts only once its writer **commits** it,
for every table it wrote at once. A committed entry carries ``visible_at`` (the commit time,
what ``as_of`` is compared with) and ``seq`` (the store's commit sequence number); a read
sees the entries with ``seq`` at or below the sequence it captured when it started, so one
read never sees half of a commit. Entries written before commits existed have neither and
count from their ``knowledge_ts``.

An entry keeps one older version of its run (``prev``), so a read whose captured sequence a
later commit of the same run has passed still finds the version it pinned. When a run commits
again before such a read reaches the partition, that version is discarded (``dropped`` on the
oldest one kept): the read raises ``StaleSnapshotError`` and ``pinned_read`` runs it again, whole,
at a fresh sequence, so a range read never mixes partitions of different commits.

A **pin** (``TableStore.pin``, ADR 0077) names a sequence whose versions must stay readable: a
commit also keeps, per pin, the newest version of the run at or below it, so the chain
(``prev`` of ``prev``) is at most pins + 2 long. A version discarded from the middle leaves
``gap`` on the version above it (the lowest sequence lost): a read whose sequence is at or above
it cannot know whether the lost version was its answer and raises ``StaleSnapshotError`` too
(below it the run is read as absent: it was first committed above that sequence). A
read given ``upto`` explicitly (``read_at``) is never retried at a fresh sequence: a pinned
reader that cannot be served says so.

A table whose runs each hold one group's whole result (``TableSpec.whole_per_group``) is also
read by its newest run per group alone (``newest_run_per_group``, ``TableStore.read_latest_runs``):
the same rows as the merge followed by "keep each group's newest run", without decoding the rest.
"""

from collections.abc import Callable, Collection, Iterator, Mapping, Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass, replace
from datetime import datetime

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc

from algotrade.storage.backends.arrow import table_spec
from algotrade.storage.tables.schemas import table_key

_ROW = "__row"
OPTIMISTIC_TRIES = 3  # reads retried at a fresh sequence before one waits out the commits


class StaleSnapshotError(Exception):
    """The versions a read pinned were replaced and discarded while it ran; the read must
    start again at a fresh commit sequence (``pinned_read`` does)."""


@dataclass(frozen=True)
class RunEntry:
    """A run's place in its partition's index."""

    knowledge_ts: pd.Timestamp
    restates: bool = False  # the run holds the partition's whole merged view as of its write
    visible_at: pd.Timestamp | None = None  # commit time; None: from knowledge_ts
    seq: int | None = None  # commit sequence number; None: always committed (or own run)
    ref: str | None = None  # where the backend keeps this version's rows (None: default)
    prev: "RunEntry | None" = None  # the version this commit replaced (same run id)
    dropped: bool = False  # an older version than this one existed and was discarded
    gap: int | None = None  # the lowest sequence of a version discarded between this and ``prev``

    @property
    def visible_from(self) -> pd.Timestamp:
        """When a read pinned at ``as_of`` starts to see the run."""
        return self.knowledge_ts if self.visible_at is None else self.visible_at


def run_mode(table: str) -> str:
    """``snapshot`` or ``merge`` per the table's spec (``snapshot`` for undeclared names)."""
    spec = table_spec(table)
    return "snapshot" if spec is None else spec.runs


def chain(entry: RunEntry | None) -> Iterator[RunEntry]:
    """``entry`` and the older versions it keeps, newest first."""
    while entry is not None:
        yield entry
        entry = entry.prev


def committed(
    knowledge_ts: pd.Timestamp,
    restates: bool,
    at: datetime,
    seq: int,
    ref: str | None,
    previous: RunEntry | None,
    pins: Collection[int] = (),
) -> RunEntry:
    """The entry a commit at ``at`` (sequence ``seq``) records. It keeps the version it
    replaces (and, per pin in ``pins``, the version that pin sees: ``retained``) so a read that
    started before the commit, or is pinned, still sees that one; it is never visible before its
    own rows were known."""
    if previous is not None and previous.seq == seq:  # re-applying the same commit
        return previous
    visible = max(pd.Timestamp(at), knowledge_ts)
    return RunEntry(knowledge_ts, restates, visible, seq, ref, retained(previous, pins))


def retained(previous: RunEntry | None, pins: Collection[int]) -> RunEntry | None:
    """The chain a commit keeps below the new version: ``previous`` itself (a read in flight) and,
    for each pin, the newest version at or below it. What goes is recorded: ``dropped`` on the
    oldest kept version when anything older was lost, ``gap`` on a kept version above a hole."""
    versions = list(chain(previous))
    if not versions:
        return None
    keep = {0}
    for pin in pins:
        for i, version in enumerate(versions):
            if version.seq is None or version.seq <= pin:
                keep.add(i)
                break
    order = sorted(keep)
    below: RunEntry | None = None
    for n in reversed(range(len(order))):  # oldest kept first, each linked to the one under it
        i = order[n]
        skipped = versions[i + 1 : order[n + 1] if n + 1 < len(order) else len(versions)]
        version = versions[i]
        if n + 1 < len(order):
            lost = [version.gap] if version.gap is not None else []
            for lower in skipped:
                lost += [lower.seq or 0, *([lower.gap] if lower.gap is not None else [])]
            below = replace(version, prev=below, gap=min(lost) if skipped else version.gap)
        elif versions[-1].dropped:  # something older than every kept version is already gone
            below = replace(version, prev=None, dropped=True, gap=None)
        else:  # the oldest kept version: what was cut below it is a gap (the run may not have
            # existed at a sequence under it: a read there is answered "absent", not stale)
            lost = [version.gap] if version.gap is not None else []
            for lower in skipped:
                lost += [lower.seq or 0, *([lower.gap] if lower.gap is not None else [])]
            below = replace(version, prev=None, gap=min(lost) if lost else None)
    return below


def max_seq(entries: Mapping[str, RunEntry], upto: int) -> int:
    """The highest commit sequence a read at ``upto`` (the published ``visible_seq``) can see in
    a partition's index: per run its newest version committed at or before ``upto`` (a commit
    in flight or crashed before publishing is not counted). An entry with no sequence (a direct
    write, or one from before ADR 0022) counts 0, so a partition holding only those is 0."""
    top = 0
    for entry in entries.values():
        version: RunEntry | None = entry
        while version is not None and version.seq is not None and version.seq > upto:
            version = version.prev
        if version is not None:
            top = max(top, version.seq or 0)
    return top


def chain_needed(entries: Mapping[str, RunEntry], pins: Collection[int]) -> bool:
    """Whether some pin may read an older version a run of ``entries`` keeps: an entry committed
    above a pin that has a version below it. Collapsing such a chain (compaction) would make that
    pin's read raise; an entry at or below every pin is what they all see."""
    return any(
        e.prev is not None and e.seq is not None and any(e.seq > p for p in pins)
        for e in entries.values()
    )


def seq_at(entries: Mapping[str, RunEntry], upto: int) -> int | None:
    """The highest sequence among the versions a read at ``upto`` sees (``max_seq`` for a pinned
    read: raises ``StaleSnapshotError`` as ``visible_entries`` does); ``None``: no run of the
    partition is visible at ``upto`` (it did not exist yet). A partition whose index holds no run
    (an empty frame was written to it) is listed live and counts 0, as ``max_seq`` does."""
    if not entries:
        return 0
    return max((e.seq or 0 for e in visible_entries(entries, upto).values()), default=None)


def listed_at(entries: Mapping[str, RunEntry], created: int | None, upto: int) -> bool:
    """Whether a read at ``upto`` lists a partition. ``created``: the sequence of the commit that
    made the partition exist with no run (an empty frame: nothing today), ``None`` when it was
    never stamped (a direct write, 0). A partition that existed by then is listed whatever it
    holds now; one with runs is listed when a version of one is visible; an unstamped partition
    with no run is always listed (it counts 0, as ``max_seq`` does)."""
    if created is not None and created <= upto:
        return True
    if not entries:
        return created is None
    return bool(visible_entries(entries, upto))


def visible_entries(entries: Mapping[str, RunEntry], upto: int | None) -> dict[str, RunEntry]:
    """Each run's version a read that captured commit sequence ``upto`` sees: commits after
    ``upto`` fall back to the version they replaced, or hide a run first committed after
    ``upto``. Raises ``StaleSnapshotError`` when the version ``upto`` saw was discarded."""
    out: dict[str, RunEntry] = {}
    for run, entry in entries.items():
        seen: RunEntry | None = entry
        while seen is not None and upto is not None and seen.seq is not None and seen.seq > upto:
            lost = (seen.prev is None and seen.dropped) or (
                seen.gap is not None and upto >= seen.gap
            )
            if lost:
                raise StaleSnapshotError(f"run {run}: the version at commit {upto} was replaced")
            seen = seen.prev
        if seen is not None:
            out[run] = seen
    return out


def pinned_read[T](
    read: Callable[[int], T],
    published: Callable[[], int],
    no_commits: Callable[[], AbstractContextManager[object]],
) -> T:
    """``read(upto)`` at one commit sequence, so it sees each commit whole or not at all.
    A ``StaleSnapshotError`` restarts it at a fresh sequence; after ``OPTIMISTIC_TRIES`` it runs
    holding ``no_commits`` (the lock commits take), where nothing can be replaced mid-read."""
    for _ in range(OPTIMISTIC_TRIES):
        try:
            return read(published())
        except StaleSnapshotError:
            continue
    with no_commits():
        return read(published())


def read_at[T](
    read: Callable[[int], T],
    published: Callable[[], int],
    no_commits: Callable[[], AbstractContextManager[object]],
    upto: int | None,
) -> T:
    """``read(upto)`` once when the caller names a sequence (a pinned reader: a
    ``StaleSnapshotError`` goes to it, never a fresh sequence), else ``pinned_read``."""
    if upto is not None:
        return read(upto)
    return pinned_read(read, published, no_commits)


def select_runs(entries: Mapping[str, RunEntry], as_of: datetime | None, mode: str) -> list[str]:
    """The runs a read at ``as_of`` combines, oldest first (see the module docstring).
    ``entries`` are already the versions the read sees (``visible_entries``)."""
    cutoff = None if as_of is None else pd.Timestamp(as_of)
    eligible = sorted(
        (entry.knowledge_ts, run)
        for run, entry in entries.items()
        if cutoff is None or entry.visible_from <= cutoff
    )
    if not eligible:
        return []
    if mode != "merge":
        return [eligible[-1][1]]
    restating = [i for i, (_, run) in enumerate(eligible) if entries[run].restates]
    start = restating[-1] if restating else 0
    return [run for _, run in eligible[start:]]


def newest_run_per_group(
    order: Sequence[str], groups: Mapping[str, Collection[tuple[object, ...]] | None]
) -> dict[tuple[object, ...], str] | None:
    """Each group's newest run, from ``order`` (the runs ``select_runs`` chose, oldest first) and
    the groups each run's rows hold (``None``: unknown, e.g. a file without statistics). ``None``
    when any run's groups are unknown or are not exactly one: the caller then merges every run
    and keeps each group's newest run from its rows (``keep_newest_runs``), so the answer never
    depends on whether the statistics exist."""
    newest: dict[tuple[object, ...], str] = {}
    for run in order:
        held = groups.get(run)
        if held is None or len(held) != 1:
            return None
        newest[next(iter(held))] = run
    return newest


def keep_newest_runs(
    frame: pd.DataFrame, group: Sequence[str], order: Sequence[str]
) -> pd.DataFrame:
    """The rows of ``frame`` (merged runs) stamped with the newest run of their group: the run
    latest in ``order`` among those holding the group (a run missing from ``order`` ranks first)."""
    if frame.empty:
        return frame
    rank = frame["run_id"].map({run: i for i, run in enumerate(order)}).fillna(-1)
    top = rank.groupby([frame[g] for g in group]).transform("max")
    return frame[rank == top].reset_index(drop=True)


def merge_rows(table: str, data: pa.Table) -> pa.Table:
    """Rows of several runs concatenated oldest run first -> one row per table key, the
    latest run's (a same-key row in a later run is a revision). Row order is kept."""
    spec = table_spec(table)
    if spec is None or data.num_rows == 0:
        return data
    key = table_key(spec, data.column_names)
    for name in key:  # runs written before a key column was declared: null, not a KeyError
        if name not in data.column_names:
            data = data.append_column(name, pa.nulls(data.num_rows))
    numbered = data.select(key).append_column(_ROW, pa.array(np.arange(data.num_rows)))
    last = numbered.group_by(key, use_threads=False).aggregate([(_ROW, "max")])
    rows = last.column(f"{_ROW}_max").combine_chunks()
    return data.take(pc.take(rows, pc.sort_indices(rows)))


def concat_frames(frames: list[pd.DataFrame]) -> pd.DataFrame | None:
    """Concatenate partitions, skipping empty ones (they carry no rows or dtypes)."""
    frames = [f for f in frames if not f.empty]
    return pd.concat(frames, ignore_index=True) if frames else None


def select_instruments(frame: pd.DataFrame, instruments: Sequence[str] | None) -> pd.DataFrame:
    if instruments is None:
        return frame.reset_index(drop=True)
    return frame[frame["instrument_id"].isin(list(instruments))].reset_index(drop=True)
