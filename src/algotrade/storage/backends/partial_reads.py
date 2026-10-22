"""Reads of part of one version file: the row groups a run, an instrument set or a ``RowFilter``
can hold, decided from the footer statistics, decoded alone and then filtered exactly. The one
place that cuts files by their row groups for ``read_run`` and ``read_runs`` (the local backend
calls it; the memory backend filters its frames with ``filter_frame``, same rows)."""

from collections.abc import Sequence
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.dataset as ds
import pyarrow.parquet as pq

from algotrade.storage.backends.arrow import keep_columns, row_groups_holding
from algotrade.storage.tables.interfaces import RowFilter, RunRead


def _column_index(meta: pq.FileMetaData, column: str) -> int | None:
    return next((i for i in range(meta.num_columns) if meta.schema.column(i).path == column), None)


def row_groups_passing(parquet: pq.ParquetFile, where: Sequence[RowFilter]) -> list[int]:
    """The row groups of ``parquet`` that can hold a row passing every filter in ``where``
    (a group without statistics, a column the file lacks or a mixed group is kept: the exact
    filter decides). ``keep`` filters rule out a group no value of which is wanted, the others
    a group whose one value (min == max, no null) is unwanted."""
    meta = parquet.metadata
    chosen = list(range(meta.num_row_groups))
    for one in where:
        index = _column_index(meta, one.column)
        if index is None:
            continue
        if one.keep:
            held = set(row_groups_holding(parquet, one.column, one.values))
            chosen = [
                g
                for g in chosen
                if g in held and not _all_null(meta.row_group(g).column(index), meta.row_group(g))
            ]
            continue
        chosen = [g for g in chosen if not _holds_only(meta.row_group(g).column(index), one)]
    return chosen


def _all_null(chunk: pq.ColumnChunkMetaData, group: pq.RowGroupMetaData) -> bool:
    """Whether the chunk holds no value (a null is in no ``keep`` set)."""
    stats = chunk.statistics
    return stats is not None and stats.has_null_count and stats.null_count == group.num_rows


def _holds_only(chunk: pq.ColumnChunkMetaData, one: RowFilter) -> bool:
    """Whether every row of the chunk is one value of ``one.values`` (so a ``keep=False`` filter
    drops the whole group): one value by the statistics and no null."""
    stats = chunk.statistics
    return (
        stats is not None
        and stats.has_min_max
        and stats.has_null_count
        and stats.null_count == 0
        and stats.min == stats.max
        and stats.min in one.values
    )


def filter_table(data: pa.Table, where: Sequence[RowFilter]) -> pa.Table:
    """``data``'s rows passing every filter (a column the table lacks is all null)."""
    for one in where:
        if one.column not in data.column_names:
            if one.keep:
                return data.slice(0, 0)
            continue
        found = pc.is_in(
            data.column(one.column).cast(pa.string()),
            value_set=pa.array(sorted(one.values), type=pa.string()),
        )
        data = data.filter(found if one.keep else pc.invert(found))
    return data


def filter_frame(frame: pd.DataFrame, where: Sequence[RowFilter]) -> pd.DataFrame:
    """``frame``'s rows passing every filter, as ``filter_table`` cuts a stored table."""
    for one in where:
        if one.column not in frame.columns:
            frame = frame.iloc[0:0] if one.keep else frame
            continue
        column = frame[one.column]
        found = column.notna() & column.astype(str).isin(one.values)
        frame = frame[found if one.keep else ~found]
    return frame


def read_run_file(
    path: Path,
    run_id: str,
    columns: Sequence[str] | None = None,
    instruments: Sequence[str] | None = None,
    where: Sequence[RowFilter] = (),
) -> pa.Table:
    """One version file's rows stamped ``run_id``: the row groups whose ``run_id`` statistics
    cannot hold it (nor, with ``instruments``, any of them in ``instrument_id``, nor, with
    ``where``, a row passing the filters) are skipped (not decoded), then the rest is filtered
    exactly. ``columns``: only those and ``keep_columns`` are decoded (and the filtered ones while
    filtering)."""
    with pq.ParquetFile(path) as parquet:
        names = parquet.schema_arrow.names
        keep = None if columns is None else keep_columns(columns) | {f.column for f in where}
        present = None if keep is None else [c for c in names if c in keep]
        if "run_id" not in names:
            data = parquet.read(columns=present)
            return _trim(filter_table(data, where), columns)
        groups = row_groups_holding(parquet, "run_id", [run_id])
        if instruments is not None and "instrument_id" in names:
            near = set(row_groups_holding(parquet, "instrument_id", instruments))
            groups = [g for g in groups if g in near]
        if where:
            passing = set(row_groups_passing(parquet, where))
            groups = [g for g in groups if g in passing]
        data = (
            parquet.read_row_groups(groups, columns=present)
            if groups
            else parquet.schema_arrow.empty_table().select(present or names)
        )
    data = filter_table(data.filter(pc.equal(data.column("run_id"), run_id)), where)
    if instruments is not None:
        ids = data.column("instrument_id")
        data = data.filter(pc.is_in(ids, value_set=pa.array(list(instruments), type=ids.type)))
    return _trim(data, columns)


def _trim(data: pa.Table, columns: Sequence[str] | None) -> pa.Table:
    """``data`` without the columns read only to filter by them."""
    if columns is None:
        return data
    keep = keep_columns(columns)
    return data.select([c for c in data.column_names if c in keep])


def require_distinct(runs: Sequence[RunRead]) -> None:
    """``read_runs`` answers by run id: a repeated one is ambiguous (``ValueError``)."""
    ids = [one.run_id for one in runs]
    if len(set(ids)) != len(ids):
        raise ValueError(f"read_runs: a run id is requested twice: {sorted(ids)}")


def read_runs_files(files: dict[str, Path], runs: Sequence[RunRead]) -> dict[str, pa.Table | None]:
    """``read_run_file`` of every request in ``runs`` (``files``: run id -> its version file),
    one dataset scan over the files filtered by ``run_id`` and (when every request names
    instruments) ``instrument_id``: the footer statistics prune the row groups, the rest is
    filtered exactly per run, its own columns (those of its file, in its order) and rows. A file
    without a ``run_id`` column has all its rows (as ``read_run_file``) and is read alone.
    ``None``: no file for the run. A file replaced mid-read raises ``FileNotFoundError``."""
    out: dict[str, pa.Table | None] = {one.run_id: None for one in runs}
    asked = [one for one in runs if one.run_id in files]
    schemas = {one.run_id: pq.read_schema(files[one.run_id]) for one in asked}
    stamped = [one for one in asked if "run_id" in schemas[one.run_id].names]
    for one in asked:
        if one not in stamped:
            out[one.run_id] = read_run_file(
                files[one.run_id], one.run_id, one.columns, one.instruments
            )
    if not stamped:
        return out
    paths = sorted({files[one.run_id] for one in stamped})
    schema = pa.unify_schemas(
        [schemas[one.run_id] for one in stamped], promote_options="permissive"
    )
    wanted = ds.field("run_id").isin(
        pa.array([one.run_id for one in stamped], schema.field("run_id").type)
    )
    if all(one.instruments is not None and "instrument_id" in schema.names for one in stamped):
        union = sorted({i for one in stamped for i in one.instruments or ()})
        wanted = wanted & ds.field("instrument_id").isin(
            pa.array(union, schema.field("instrument_id").type)
        )
    if any(one.columns is None for one in stamped):
        columns = None
    else:
        keep = set().union(*(keep_columns(one.columns or ()) for one in stamped))
        columns = [c for c in schema.names if c in keep or c == "run_id"]
    data = ds.dataset([str(p) for p in paths], schema=schema, format="parquet").to_table(
        columns=columns, filter=wanted
    )
    by_run = _split_by_run(data)
    for one in stamped:
        mine = by_run.get(one.run_id, data.slice(0, 0))
        if one.instruments is not None:
            ids = mine.column("instrument_id")
            mine = mine.filter(
                pc.is_in(ids, value_set=pa.array(list(one.instruments), type=ids.type))
            )
        own = [n for n in schemas[one.run_id].names if n in mine.column_names]
        mine = mine.select(own)
        out[one.run_id] = _trim(mine, one.columns)
    return out


def _split_by_run(data: pa.Table) -> dict[str, pa.Table]:
    """``data``'s rows per ``run_id``, each run's in their order in ``data``: one stable sort and
    slices, not one filter pass per run."""
    if data.num_rows == 0:
        return {}
    ordered = data.take(pc.sort_indices(data, sort_keys=[("run_id", "ascending")]))
    counts = pc.value_counts(ordered.column("run_id"))  # the sorted runs, in order
    parts: dict[str, pa.Table] = {}
    start = 0
    for item in counts.to_pylist():
        parts[item["values"]] = ordered.slice(start, item["counts"])
        start += item["counts"]
    return parts
