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
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc

from algotrade.storage.backends.arrow import table_spec
from algotrade.storage.tables.schemas import table_key

_ROW = "__row"


@dataclass(frozen=True)
class RunEntry:
    """A run's place in its partition's index."""

    knowledge_ts: pd.Timestamp
    restates: bool = False  # the run holds the partition's whole merged view as of its write
    visible_at: pd.Timestamp | None = None  # commit time; None: from knowledge_ts
    seq: int | None = None  # commit sequence number; None: always committed (or own run)
    ref: str | None = None  # where the backend keeps this version's rows (None: default)
    prev: "RunEntry | None" = None  # the version this commit replaced (same run id)

    @property
    def visible_from(self) -> pd.Timestamp:
        """When a read pinned at ``as_of`` starts to see the run."""
        return self.knowledge_ts if self.visible_at is None else self.visible_at


def run_mode(table: str) -> str:
    """``snapshot`` or ``merge`` per the table's spec (``snapshot`` for undeclared names)."""
    spec = table_spec(table)
    return "snapshot" if spec is None else spec.runs


def committed(
    knowledge_ts: pd.Timestamp,
    restates: bool,
    at: datetime,
    seq: int,
    ref: str | None,
    previous: RunEntry | None,
) -> RunEntry:
    """The entry a commit at ``at`` (sequence ``seq``) records. It keeps the version it
    replaces (one level) so a read that started before the commit still sees that one; it
    is never visible before its own rows were known."""
    if previous is not None and previous.seq == seq:  # re-applying the same commit
        return previous
    old = None if previous is None else replace(previous, prev=None)
    visible = max(pd.Timestamp(at), knowledge_ts)
    return RunEntry(knowledge_ts, restates, visible, seq, ref, old)


def visible_entries(entries: Mapping[str, RunEntry], upto: int | None) -> dict[str, RunEntry]:
    """Each run's version a read that captured commit sequence ``upto`` sees: commits after
    ``upto`` fall back to the version they replaced, or hide the run."""
    out: dict[str, RunEntry] = {}
    for run, entry in entries.items():
        seen: RunEntry | None = entry
        while seen is not None and upto is not None and seen.seq is not None and seen.seq > upto:
            seen = seen.prev
        if seen is not None:
            out[run] = seen
    return out


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


def merge_rows(table: str, data: pa.Table) -> pa.Table:
    """Rows of several runs concatenated oldest run first -> one row per table key, the
    latest run's (a same-key row in a later run is a revision). Row order is kept."""
    spec = table_spec(table)
    if spec is None or data.num_rows == 0:
        return data
    key = table_key(spec, data.column_names)
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
