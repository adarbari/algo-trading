"""History copy: a derived, read-optimised copy of a table's resolved rows (ADR 0060).

Reading a long range of a table partition by partition opens one file per session day (14,000
for a market table since 1971). The copy holds the same rows in one Parquet file per calendar
year, sorted by ``(instrument_id, session_date)`` in row groups of ``ROW_GROUP_ROWS`` rows, so
a one-instrument read opens one file and decodes one row group per year.

Layout under ``tables/<table>/_history/`` (a derived artefact outside every run's atomic
publish; deleting the folder loses nothing)::

    manifest.json               per year: the file, the commit sequence it was built at, its
                                row count and the signature of each source partition's index
    year=YYYY~<hex>.parquet     the rows ``select_runs`` / ``merge_rows`` resolve at ``as_of``
                                None, plus ``__day`` (the partition) and ``__pos`` (the row's
                                position in that partition's resolved frame, so a read restores
                                the partition path's row order exactly)

**Staleness (exact, per partition).** A partition's index (``_runs.json``) is replaced by a
rename on every commit, restate or purge, so its ``(inode, mtime, size)`` names the version of
everything that partition resolves to. A year's copy serves a read only when every calendar day
of the requested range inside that year has the signature the build recorded (``None`` for a
day with no partition): a changed, new or purged partition, or a restored store, fails the
check and the read falls back to the partitions. The check is one ``stat`` per requested day.
It is stricter than comparing commit sequence numbers, which move on every commit to any
table, and never looser: a signature can only match an index that was not replaced since the
build, and the build refuses sources a commit had applied but not yet published.

Only the ingestion writer builds (``build``); the files are written to a unique name and the
manifest, replaced atomically last, is what makes them visible. A copy that cannot be read is
treated as stale. The copy serves reads with ``as_of`` None and no ``own_run`` (those resolve
to exactly what it holds); anything else reads partitions.
"""

import json
import logging
import secrets
import threading
from collections.abc import Callable, Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from algotrade.storage.backends.arrow import concat, keep_columns, parquet_bytes
from algotrade.storage.backends.local_index import INDEX, atomic_write, read_index
from algotrade.storage.backends.run_selection import StaleSnapshotError, pinned_read
from algotrade.storage.locks import FileLock, held

log = logging.getLogger(__name__)

HISTORY = "_history"
MANIFEST = "manifest.json"
ROW_GROUP_ROWS = 50_000  # small enough that one instrument's rows live in one or two groups
MIN_UNFILTERED_DAYS = 180  # an all-instrument read of fewer days opens fewer partition files
DAY = "__day"
POS = "__pos"
FORMAT = 1


@dataclass(frozen=True)
class YearCopy:
    """One built year: its file, the commit sequence it was built at, its source partitions."""

    file: str | None  # None: the year's partitions held no rows
    seq: int
    rows: int
    days: dict[str, str]  # ISO date -> signature of the partition's index
    ragged: frozenset[str] = frozenset()  # ISO dates whose partition schema is not the file's


Resolve = Callable[[date, int], pa.Table | None]  # (day, commit sequence) -> the resolved rows


class HistoryCopy:
    """The history copies of one store's tables: reads (``usable`` + ``read_year``) and the
    writer (``build``)."""

    def __init__(
        self,
        tables_root: Path,
        published: Callable[[], int],
        no_commits: Callable[[], AbstractContextManager[object]],
    ) -> None:
        self.root = tables_root
        self._published = published
        self._no_commits = no_commits
        # table -> (the manifest file's stat when parsed, its years): parsed once per version
        self._parsed: dict[str, tuple[tuple[int, int, int], dict[int, YearCopy]]] = {}
        self._guard = threading.Lock()

    def _folder(self, table: str) -> Path:
        return self.root / table / HISTORY

    def _partition(self, table: str, day: date | str) -> Path:
        name = day if isinstance(day, str) else day.isoformat()
        return self.root / table / f"date={name}"

    def _signature(self, table: str, day: date | str) -> str | None:
        """The version of a partition's index: changes on every commit, restate or purge."""
        try:
            st = (self._partition(table, day) / INDEX).stat()
        except FileNotFoundError:
            return None
        return f"{st.st_ino}:{st.st_mtime_ns}:{st.st_size}"

    # ------------------------------------------------------------------------ reading

    def years(self, table: str) -> dict[int, YearCopy]:
        """The years the table's manifest lists (empty when it has none, or it is unreadable)."""
        path = self._folder(table) / MANIFEST
        try:
            st = path.stat()
            stamp = (st.st_ino, st.st_mtime_ns, st.st_size)
            with self._guard:
                held_ = self._parsed.get(table)
            if held_ is not None and held_[0] == stamp:
                return held_[1]
            loaded = json.loads(path.read_text())
            years = {
                int(y): YearCopy(
                    v["file"],
                    int(v["seq"]),
                    int(v["rows"]),
                    dict(v["days"]),
                    frozenset(v.get("ragged", ())),
                )
                for y, v in loaded["years"].items()
            }
        except FileNotFoundError:
            return {}
        except (ValueError, KeyError, TypeError, OSError) as exc:  # a damaged manifest: no copy
            log.warning("history copy of %s ignored: unreadable manifest (%s)", table, exc)
            return {}
        with self._guard:
            self._parsed[table] = (stamp, years)
        return years

    def usable(
        self, table: str, start: date, end: date, filtered: bool, upto: int
    ) -> dict[int, YearCopy]:
        """The years whose copy serves a read of ``[start, end]`` (``filtered``: of named
        instruments) captured at commit ``upto``: every requested day of the year still has the
        signature the build recorded. A year read for all instruments over a short stretch is
        left to its partitions (``MIN_UNFILTERED_DAYS``)."""
        out: dict[int, YearCopy] = {}
        for year, copy in self.years(table).items():
            low, high = max(start, date(year, 1, 1)), min(end, date(year, 12, 31))
            if low > high or copy.seq > upto:
                continue
            if not filtered and (high - low).days + 1 < MIN_UNFILTERED_DAYS:
                continue
            if all(
                self._signature(table, day) == copy.days.get(day.isoformat())
                and day.isoformat() not in copy.ragged
                for day in _each_day(low, high)
            ):
                out[year] = copy
        return out

    def read_year(
        self,
        table: str,
        year: int,
        copy: YearCopy,
        start: date,
        end: date,
        instruments: Sequence[str] | None,
        columns: Sequence[str] | None,
    ) -> pa.Table | None:
        """The year's rows of ``[start, end]`` (and ``instruments``) in the partition path's
        order, helper columns removed; ``None`` when the copy cannot be read (a rebuild
        replaced its file, or it is damaged): the caller reads the partitions."""
        if copy.file is None:
            return pa.table({})
        try:
            with pq.ParquetFile(self._folder(table) / copy.file) as parquet:
                names = parquet.schema_arrow.names
                keep = None if columns is None else keep_columns(columns) | {DAY, POS}
                present = [n for n in names if keep is None or n in keep]
                groups = _row_groups(parquet, instruments)
                data = parquet.read_row_groups(groups, columns=present)
        except (OSError, pa.ArrowInvalid) as exc:
            log.warning("history copy of %s %s skipped: %s", table, year, exc)
            return None
        keep_rows = pc.and_(
            pc.greater_equal(data.column(DAY), pa.scalar(start, pa.date32())),
            pc.less_equal(data.column(DAY), pa.scalar(end, pa.date32())),
        )
        if instruments is not None:
            ids = data.column("instrument_id")
            wanted = pc.is_in(ids, value_set=pa.array(list(instruments), type=ids.type))
            keep_rows = pc.and_(keep_rows, wanted)
        data = data.filter(keep_rows)
        order = pc.sort_indices(data, sort_keys=[(DAY, "ascending"), (POS, "ascending")])
        return data.take(order).drop_columns([DAY, POS])

    # ------------------------------------------------------------------------ building

    def build(
        self, table: str, years: Sequence[int], days: Sequence[date], resolve: Resolve
    ) -> list[int]:
        """Make the copy hold exactly ``years`` (those with partitions) and be current: a year
        whose copy is still fresh is kept, any other is built from ``days`` (the table's
        partitions) through ``resolve``; years not listed are removed. -> the years built."""
        wanted = sorted({y for y in years if any(d.year == y for d in days)})
        folder = self._folder(table)
        built: list[int] = []
        kept: dict[int, YearCopy] = {}
        folder.mkdir(parents=True, exist_ok=True)
        with held(FileLock(folder / ".build.lock")):
            current = self.years(table)
            for year in wanted:
                old = current.get(year)
                whole = (date(year, 1, 1), date(year, 12, 31))
                if old is not None and self._reusable(table, old, *whole):
                    kept[year] = old
                    continue
                mine = [d for d in days if d.year == year]

                def read_at(upto: int, mine: list[date] = mine) -> YearCopy:
                    return self._build_year(table, mine, resolve, upto)

                kept[year] = pinned_read(read_at, self._published, self._no_commits)
                built.append(year)
            payload = {
                "format": FORMAT,
                "years": {
                    str(y): {
                        "file": c.file,
                        "seq": c.seq,
                        "rows": c.rows,
                        "days": c.days,
                        "ragged": sorted(c.ragged),
                    }
                    for y, c in sorted(kept.items())
                },
            }
            atomic_write(folder / MANIFEST, json.dumps(payload, sort_keys=True).encode())
            used = {c.file for c in kept.values()}
            for path in (*folder.glob("year=*.parquet"), *folder.glob(".year=*.tmp")):
                if path.name not in used:  # also the temp file a crashed build left
                    path.unlink(missing_ok=True)
        return built

    def _reusable(self, table: str, copy: YearCopy, low: date, high: date) -> bool:
        exists = copy.file is None or (self._folder(table) / copy.file).exists()
        return exists and all(
            self._signature(table, day) == copy.days.get(day.isoformat())
            for day in _each_day(low, high)
        )

    def _build_year(
        self, table: str, days: Sequence[date], resolve: Resolve, upto: int
    ) -> YearCopy:
        """One year's file from ``days`` at commit ``upto``. ``StaleSnapshotError`` (the
        caller reads again at a fresh sequence) when a partition's index holds a commit
        ``upto`` does not include, or changed while the rows were read."""
        before = {d.isoformat(): self._signature(table, d) for d in days}
        parts: list[pa.Table] = []
        shapes: dict[str, list[tuple[str, str]]] = {}
        for day in days:
            if any(
                e.seq is not None and e.seq > upto
                for e in read_index(self._partition(table, day)).values()
            ):
                raise StaleSnapshotError(f"{table} {day}: a commit above {upto} is applied")
            data = resolve(day, upto)
            if data is None:
                continue
            shapes[day.isoformat()] = _shape(data)  # an empty partition's columns count too
            if data.num_rows == 0:
                continue
            marked = data.append_column(DAY, pa.array([day] * data.num_rows, pa.date32()))
            parts.append(
                marked.append_column(POS, pa.array(np.arange(data.num_rows, dtype=np.int32)))
            )
        if before != {d.isoformat(): self._signature(table, d) for d in days}:
            raise StaleSnapshotError(f"{table}: a partition changed while its year was built")
        signatures = {k: v for k, v in before.items() if v is not None}
        if not parts:
            return YearCopy(None, upto, 0, signatures)
        data = concat(table, parts)
        if "instrument_id" not in data.column_names:
            raise ValueError(f"{table} has no instrument_id column: no history copy")
        order = pc.sort_indices(
            data, sort_keys=[("instrument_id", "ascending"), (DAY, "ascending"), (POS, "ascending")]
        )
        data = data.take(order)
        whole = _shape(data.drop_columns([DAY, POS]))
        # a day whose partition lacks a column the year has (one added mid-year) reads without
        # it on the partition path: such a year serves only the days that match the file
        ragged = frozenset(day for day, shape in shapes.items() if shape != whole)
        name = f"year={days[0].year}~{secrets.token_hex(4)}.parquet"
        atomic_write(self._folder(table) / name, parquet_bytes(data, ROW_GROUP_ROWS))
        return YearCopy(name, upto, data.num_rows, signatures, ragged)


def _shape(data: pa.Table) -> list[tuple[str, str]]:
    return [(f.name, str(f.type)) for f in data.schema]


def _each_day(low: date, high: date) -> list[date]:
    return [low + timedelta(days=i) for i in range((high - low).days + 1)]


def _row_groups(parquet: pq.ParquetFile, instruments: Sequence[str] | None) -> list[int]:
    """The row groups whose ``instrument_id`` range can hold one of ``instruments`` (all of
    them for no filter, or a group without statistics)."""
    meta = parquet.metadata
    if instruments is None:
        return list(range(meta.num_row_groups))
    column = next(
        i for i in range(meta.num_columns) if meta.schema.column(i).path == "instrument_id"
    )
    wanted = sorted(set(instruments))
    chosen: list[int] = []
    for group in range(meta.num_row_groups):
        stats = meta.row_group(group).column(column).statistics
        if stats is None or not stats.has_min_max:
            chosen.append(group)
            continue
        low, high = stats.min, stats.max
        if any(low <= w <= high for w in wanted):
            chosen.append(group)
    return chosen
