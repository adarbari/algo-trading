"""Reads of part of one version file: the row groups a run, an instrument set or a ``RowFilter``
can hold, decided from the footer statistics, decoded alone and then filtered exactly. The one
place that cuts a file by its row groups for ``read_run`` (the local backend calls it; the memory
backend filters its frames with ``filter_frame``, same rows)."""

from collections.abc import Sequence
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from algotrade.storage.backends.arrow import keep_columns, row_groups_holding
from algotrade.storage.tables.interfaces import RowFilter


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
