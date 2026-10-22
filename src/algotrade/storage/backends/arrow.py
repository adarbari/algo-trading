"""Frames <-> Arrow tables under the declared table schemas (``storage/tables/schemas.py``).

Shared by every backend so they cannot disagree: a write casts each declared column to its
type (``ARROW_TYPES``), fails on uncastable data, nulls in a non-nullable column or an
undeclared column of a fixed table, and stamps the table name and ``SCHEMA_VERSION`` into the
schema metadata. A read casts each declared column of a file to today's type, so files
written before the schemas were typed (``string`` vs ``large_string``, all-null columns,
``int64`` trades) read as if they were written today. Parquet layout lives here too.
"""

import io
from collections.abc import Collection, Iterable, Sequence
from itertools import pairwise
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from algotrade.core.model.errors import DataValidationError
from algotrade.storage.tables.interfaces import PartitionStats
from algotrade.storage.tables.schemas import KNOWN_FROM, spec_for
from algotrade.storage.tables.spec import COMMON, SCHEMA_VERSION, TableSpec

ARROW_TYPES: dict[str, pa.DataType] = {
    "string": pa.large_string(),
    "float64": pa.float64(),
    "float32": pa.float32(),
    "int64": pa.int64(),
    "bool": pa.bool_(),
    "date": pa.date32(),
    "timestamp_utc": pa.timestamp("us", tz="UTC"),
    "float64[]": pa.list_(pa.float64()),
    "float32[]": pa.list_(pa.float32()),
    "int64[]": pa.list_(pa.int64()),
    "string[]": pa.list_(pa.large_string()),
    "date[]": pa.list_(pa.date32()),
}
TABLE_KEY = b"algotrade.table"
VERSION_KEY = b"algotrade.schema_version"
# ~64k rows per row group, with a page index: filtered reads (instrument_id, underlying_id)
# skip row groups and pages whose statistics cannot match.
ROW_GROUP_SIZE = 64 * 1024
_CAST_ERRORS = (pa.ArrowInvalid, pa.ArrowTypeError, pa.ArrowNotImplementedError)


def table_spec(table: str) -> TableSpec | None:
    """The declared spec, or ``None`` for a name no spec covers (backends store it as is)."""
    try:
        return spec_for(table)
    except DataValidationError:
        return None


def to_arrow(table: str, frame: pd.DataFrame) -> pa.Table:
    """A frame as it will be stored: declared types, stamped. Raises ``DataValidationError``."""
    try:
        data = pa.Table.from_pandas(frame, preserve_index=False)
    except _CAST_ERRORS as exc:
        raise DataValidationError(table, [f"not storable as columns: {exc}"]) from exc
    data = conform(table, data, strict=True)
    return data.replace_schema_metadata(
        {TABLE_KEY: table.encode(), VERSION_KEY: str(SCHEMA_VERSION).encode()}
    )


def conform(table: str, data: pa.Table, strict: bool = False) -> pa.Table:
    """Cast every declared column present to its declared type. ``strict`` (writes) also
    rejects undeclared columns of fixed tables and nulls where the schema forbids them."""
    spec = table_spec(table)
    if spec is None:
        return data
    fields, arrays, problems = [], [], []
    for name in data.column_names:
        column, values = spec.column(name), data.column(name)
        if column is None:
            if strict and not spec.open_ended:
                problems.append(f"undeclared column {name!r}")
            fields.append(data.schema.field(name))
            arrays.append(values)
            continue
        target = ARROW_TYPES[column.type]
        try:
            cast = values if values.type == target else pc.cast(values, target, safe=True)
        except _CAST_ERRORS as exc:
            problems.append(f"{name}: cannot store {values.type} as {column.type}: {exc}")
            continue
        if strict and not column.nullable and cast.null_count:
            problems.append(f"{name}: nulls in a non-nullable column")
        fields.append(pa.field(name, target, nullable=column.nullable))
        arrays.append(cast)
    if problems:
        raise DataValidationError(table, problems)
    # pandas' own metadata describes the frame before the casts; Arrow types are the truth.
    metadata = {k: v for k, v in (data.schema.metadata or {}).items() if k != b"pandas"}
    return pa.Table.from_arrays(arrays, schema=pa.schema(fields, metadata=metadata))


def concat(table: str, parts: list[pa.Table]) -> pa.Table:
    """Partitions of one table, conformed. Fixed tables then share one schema (missing
    columns fill with nulls); open-ended ones may differ in producer-defined columns, so only
    there are types widened (``permissive``)."""
    spec = table_spec(table)
    promote = "permissive" if spec is None or spec.open_ended else "default"
    return pa.concat_tables([conform(table, p) for p in parts], promote_options=promote)


def keep_columns(columns: Iterable[str]) -> set[str]:
    """A column-pruned read keeps these as well: the row key and the point-in-time columns
    (with an event row's ``known_from``, ADR 0050)."""
    return {*columns, *COMMON, KNOWN_FROM, "instrument_id", "ts", "change"}


def parquet_bytes(data: pa.Table, row_group_size: int = ROW_GROUP_SIZE) -> bytes:
    sink = io.BytesIO()
    pq.write_table(
        data, sink, compression="zstd", row_group_size=row_group_size, write_page_index=True
    )
    return sink.getvalue()


def table_parquet_bytes(table: str, data: pa.Table) -> bytes:
    """``data`` as ``table``'s file: ``parquet_bytes``, or, for a table declaring ``cluster_by``,
    its rows stably sorted by those columns and one run of row groups per distinct value
    combination, so the footer statistics name each group's values (``row_groups_passing``).
    A table that also declares ``row_group_rows`` is cut into groups of that many rows instead
    (several values share a group, its min / max still bound them: a many-valued column such as
    ``instrument_id``). Deterministic: the same rows give the same bytes."""
    spec = table_spec(table)
    if spec is None or not spec.cluster_by or data.num_rows == 0:
        return parquet_bytes(data)
    by = [c for c in spec.cluster_by if c in data.column_names]
    if not by:
        return parquet_bytes(data)
    data = data.take(pc.sort_indices(data, sort_keys=[(c, "ascending") for c in by]))
    if spec.row_group_rows is not None:
        return parquet_bytes(data, spec.row_group_rows)
    keys = data.select(by).to_pylist()
    starts = [0, *(i for i in range(1, len(keys)) if keys[i] != keys[i - 1]), len(keys)]
    sink = io.BytesIO()
    with pq.ParquetWriter(sink, data.schema, compression="zstd", write_page_index=True) as writer:
        for begin, end in pairwise(starts):
            writer.write_table(data.slice(begin, end - begin), row_group_size=ROW_GROUP_SIZE)
    return sink.getvalue()


def is_clustered(path: Path, table: str) -> bool:
    """Whether the file at ``path`` is laid out as ``table`` declares when it declares
    ``row_group_rows`` (``table_parquet_bytes``): every row group within that size and the first
    ``cluster_by`` column non-decreasing over the file. The footer answers first; only a file that
    passes it has the one column read. Any other table is always laid out as declared."""
    spec = table_spec(table)
    if spec is None or not spec.cluster_by or spec.row_group_rows is None:
        return True
    first = spec.cluster_by[0]
    with pq.ParquetFile(path) as parquet:
        meta = parquet.metadata
        names = {meta.schema.column(i).path: i for i in range(meta.num_columns)}
        if first not in names:
            return True  # an empty file or one from before the column: nothing to cluster
        highest: object = None
        for number in range(meta.num_row_groups):
            group = meta.row_group(number)
            stats = group.column(names[first]).statistics
            if group.num_rows > spec.row_group_rows or stats is None or not stats.has_min_max:
                return False
            if highest is not None and stats.min < highest:
                return False
            highest = stats.max
        column = parquet.read(columns=[first]).column(0).combine_chunks()
    return len(column) < 2 or bool(pc.all(pc.less_equal(column[:-1], column[1:])).as_py())


def to_frame(data: pa.Table) -> pd.DataFrame:
    frame: pd.DataFrame = data.to_pandas()
    return frame


def row_groups_holding(parquet: pq.ParquetFile, column: str, values: Collection[str]) -> list[int]:
    """The row groups of ``parquet`` whose ``column`` min / max statistics can hold one of
    ``values`` (a group without statistics is kept): the others need not be decoded."""
    meta = parquet.metadata
    index = next(i for i in range(meta.num_columns) if meta.schema.column(i).path == column)
    wanted = sorted(set(values))
    chosen: list[int] = []
    for group in range(meta.num_row_groups):
        stats = meta.row_group(group).column(index).statistics
        if (
            stats is None
            or not stats.has_min_max
            or any(stats.min <= w <= stats.max for w in wanted)
        ):
            chosen.append(group)
    return chosen


def footer_groups(meta: pq.FileMetaData, group: Sequence[str]) -> set[tuple[object, ...]] | None:
    """The groups (values of the ``group`` columns) a file holds, from its footer alone: every
    row group's statistics must name one value per column (min == max) and no null. ``None``: a
    column missing, a row group without statistics, or one holding two values or a null."""
    at = {meta.schema.column(i).path: i for i in range(meta.num_columns)}
    if any(name not in at for name in group):
        return None
    found: set[tuple[object, ...]] = set()
    for number in range(meta.num_row_groups):
        values = []
        for name in group:
            stats = meta.row_group(number).column(at[name]).statistics
            if stats is None or not stats.has_min_max or stats.min != stats.max:
                return None
            if stats.null_count:
                return None
            values.append(stats.min)
        found.add(tuple(values))
    return found


def file_groups(path: Path, group: Sequence[str]) -> set[tuple[object, ...]] | None:
    """``footer_groups`` of the file at ``path``."""
    with pq.ParquetFile(path) as parquet:
        return footer_groups(parquet.metadata, group)


def file_stats(path: Path, column: str | None) -> PartitionStats:
    """What one version file holds, without decoding it: its rows (the footer's ``num_rows``),
    the sorted ``run_id`` values (the footer's statistics; the one column decoded when they
    cannot name them) and, when ``column`` is in the file, that column's values as text (only
    it decoded)."""
    with pq.ParquetFile(path) as parquet:
        rows = parquet.metadata.num_rows
        names = parquet.schema_arrow.names
        if rows == 0:
            return PartitionStats(0)
        named = footer_groups(parquet.metadata, ["run_id"]) if "run_id" in names else set()
        wanted = [c for c in ("run_id", column) if c in names and (c == column or named is None)]
        data = parquet.read(columns=wanted) if wanted else None
    if named is None:
        assert data is not None
        runs = tuple(sorted(map(str, data.column("run_id").to_pandas().unique())))
    else:
        runs = tuple(sorted(str(v) for (v,) in named))
    values: tuple[str, ...] = ()
    if column is not None and data is not None and column in data.column_names:
        values = tuple(map(str, data.column(column).to_pandas()))
    return PartitionStats(rows, runs, values)
