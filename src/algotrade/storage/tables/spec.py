"""The vocabulary of a table schema: abstract column types, the run modes, ``Column`` and
``TableSpec``, and the builders (``fixed``, ``strings``, ``floats``) the declarations of
``schemas.py`` and ``edge_schemas.py`` are written with. Declares no table itself."""

from dataclasses import dataclass

# Stamped into every Parquet file's metadata with the table name (storage backends). Bump it
# when a declared type changes; readers cast older files to today's declared types.
SCHEMA_VERSION = 1
COMMON = ("session_date", "knowledge_ts", "source", "run_id")
# Abstract column types; storage backends map them to physical types (Arrow, DuckDB later).
# ``<scalar>[]`` is a list column of that scalar (ADR 0063's per-session arrays, ADR 0064's
# per-pick ones); the list null or empty, an element null (never 0).
COLUMN_TYPES = frozenset(
    {
        "string", "float64", "float32", "int64", "bool", "date", "timestamp_utc",
        "float64[]", "float32[]", "int64[]", "string[]", "date[]",
    }
)  # fmt: skip
# How a partition's runs combine on read: "snapshot" (each run is the whole partition; the
# latest known at as_of wins) or "merge" (each run is a window; the union, latest per key).
RUN_MODES = frozenset({"snapshot", "merge"})


@dataclass(frozen=True)
class Column:
    name: str
    type: str  # one of COLUMN_TYPES
    nullable: bool = True

    def __post_init__(self) -> None:
        if self.type not in COLUMN_TYPES:
            raise ValueError(f"{self.name}: unknown column type {self.type!r}")


@dataclass(frozen=True)
class TableSpec:
    """A table's contract. ``columns`` declares types: every column of a fixed table (others
    are rejected on write); the common and key columns of an open-ended one (the producer
    defines the rest). Writes cast to the declared types and fail on uncastable data.
    ``runs`` says how a partition's runs combine on read (``RUN_MODES``); ``key``, when set,
    is the table key (``table_key``) instead of the grain's default. ``retention_days``, when
    set, is the default retention window: only such tables may have old partitions purged
    (``purge_before``); every other table is history, kept forever. ``whole_per_group``: each
    run's file holds its (user, config) group's whole result, so the group's newest run alone
    answers a read (``TableStore.read_latest_runs``); a table that compaction trims to changed
    rows (ADR 0078) never sets it."""

    name: str
    grain: str
    required: tuple[str, ...]
    open_ended: bool = False
    columns: tuple[Column, ...] = ()
    runs: str = "snapshot"
    key: tuple[str, ...] = ()
    retention_days: int | None = None
    whole_per_group: bool = False

    def __post_init__(self) -> None:
        if self.runs not in RUN_MODES:
            raise ValueError(f"{self.name}: unknown run mode {self.runs!r}")
        if self.whole_per_group and (
            self.runs != "merge" or not {"user_id", "config_id"} <= set(self.key)
        ):
            raise ValueError(
                f"{self.name}: whole_per_group needs a merge table keyed by user, config"
            )

    def column(self, name: str) -> Column | None:
        return next((c for c in self.columns if c.name == name), None)


def columns_of(*specs: str) -> tuple[Column, ...]:
    """``"name type"`` (``type!``: not nullable) + the point-in-time columns."""
    out = []
    for spec in (*specs, "session_date date!", "knowledge_ts timestamp_utc!", "source string!",
                 "run_id string!"):  # fmt: skip
        name, kind = spec.split()
        out.append(Column(name, kind.rstrip("!"), not kind.endswith("!")))
    return tuple(out)


def fixed(
    name: str,
    grain: str,
    required: tuple[str, ...],
    *columns: str,
    runs: str = "snapshot",
    key: tuple[str, ...] = (),
    retention_days: int | None = None,
    whole_per_group: bool = False,
) -> TableSpec:
    spec = TableSpec(
        name, grain, required, columns=columns_of(*columns), runs=runs, key=key,
        retention_days=retention_days, whole_per_group=whole_per_group,
    )  # fmt: skip
    undeclared = [c for c in (*COMMON, *required, *key) if spec.column(c) is None]
    if undeclared:
        raise ValueError(f"{name}: required columns without a type: {undeclared}")
    return spec


def strings(*names: str) -> tuple[str, ...]:
    return tuple(f"{n} string" for n in names)


def floats(*names: str) -> tuple[str, ...]:
    return tuple(f"{n} float64" for n in names)
