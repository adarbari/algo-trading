"""Field names for stored data, shared by configs (selections) and storage (views).

- ``instrument.<column>``          L1 reference facts (``instruments/reference``); company
                                   columns (``COMPANY_FIELDS``) come from ``instruments/company``
- ``rollup.<name>@v<N>.<column>``  a rollup (``rollups/instrument/<name>@v<N>``)
- ``market.<name>@v<N>.<column>``  a market-entity feature group (``rollups/market/<name>@v<N>``,
                                   one ``MKT:<market>`` row per session; ADR 0047)
- ``feature.<name>``               an expression feature (``config/site/features/*.toml``),
                                   computed on read from the stored features it names

A feature group's table is ``rollup_table(entity, key)``: the ``rollups/<entity>/`` family
of what one row describes (``GROUP_TABLE_PREFIXES``); ``group_field`` / ``table_field`` name
a column of one as a field.
"""

from algotrade.core.model.errors import ConfigurationError

REFERENCE_TABLE = "instruments/reference"
COMPANY_TABLE = "instruments/company"
DESCRIPTION_TABLE = "instruments/description"  # what a company or fund is about (ADR 0034)
ROLLUP_TABLE_PREFIX = "rollups/instrument/"
MARKET_ROLLUP_PREFIX = "rollups/market/"  # market-entity feature groups (ADR 0047)
# What one row of a feature group describes -> its table family and its field head.
GROUP_TABLE_PREFIXES = {"instrument": ROLLUP_TABLE_PREFIX, "market": MARKET_ROLLUP_PREFIX}
GROUP_FIELD_HEADS = {"instrument": "rollup", "market": "market"}
FEATURE_FIELD_PREFIX = "feature."
# The value types a field (an instrument column or a declared rollup column) may have.
# ``float32``: a 32-bit float stored to halve the bytes (feature groups from ADR 0023 step 3).
FIELD_TYPES = frozenset({"str", "float", "float32", "int", "bool", "date"})
NUMERIC_TYPES = frozenset({"float", "float32", "int"})
# ``instruments/company`` columns, in order, as the company source produces them.
COMPANY_COLUMNS = (
    "cik",
    "name",
    "entity_type",
    "sic",
    "sic_description",
    "sic_division",
    "sector",
    "industry",
    "state_of_incorporation",
    "fiscal_year_end",
    "website",
    "former_names",
    "exchanges",
    "tickers",
)
# instrument.<column> fields read from the company table rather than the reference.
COMPANY_FIELDS = frozenset(COMPANY_COLUMNS[3:11])


def instrument_field(column: str) -> str:
    return f"instrument.{column}"


def rollup_field(rollup: str, column: str) -> str:
    """``rollup`` is ``<name>@v<N>``."""
    return f"rollup.{rollup}.{column}"


def rollup_table(entity: str, key: str) -> str:
    """The table of the feature group ``key`` (``<name>@v<N>``) of ``entity``:
    ``rollups/instrument/<key>`` or ``rollups/market/<key>``."""
    if entity not in GROUP_TABLE_PREFIXES:
        raise ConfigurationError(f"{key}: no table family for entity {entity!r}")
    return f"{GROUP_TABLE_PREFIXES[entity]}{key}"


def group_field(entity: str, key: str, column: str) -> str:
    """The selection field of a group column: ``rollup.<key>.<column>`` for an instrument
    group, ``market.<key>.<column>`` for a market one."""
    if entity not in GROUP_FIELD_HEADS:
        raise ConfigurationError(f"{key}: no field for entity {entity!r}")
    return f"{GROUP_FIELD_HEADS[entity]}.{key}.{column}"


def group_of_table(table: str) -> tuple[str, str] | None:
    """``(entity, key)`` of a feature group's table, ``None`` for any other table."""
    for entity, prefix in GROUP_TABLE_PREFIXES.items():
        if table.startswith(prefix) and len(table) > len(prefix):
            return entity, table.removeprefix(prefix)
    return None


def table_field(table: str, column: str) -> str:
    """The field reading ``column`` of the feature group table ``table`` (``field_source``'s
    inverse)."""
    found = group_of_table(table)
    if found is None:
        raise ConfigurationError(f"{table} is not a feature group table")
    return group_field(*found, column)


def is_feature_field(field_name: str) -> bool:
    """``feature.<name>``: an expression feature, computed on read (no table of its own)."""
    return field_name.startswith(FEATURE_FIELD_PREFIX)


def field_source(field_name: str) -> tuple[str, str]:
    """``(table, column)`` a field is read from (not for ``feature.<name>``: computed)."""
    head, _, rest = field_name.partition(".")
    if head == "instrument" and rest:
        return (COMPANY_TABLE if rest in COMPANY_FIELDS else REFERENCE_TABLE), rest
    entities = {h: e for e, h in GROUP_FIELD_HEADS.items()}
    if head in entities and "." in rest:
        key, _, column = rest.rpartition(".")
        return rollup_table(entities[head], key), column
    if head == "feature":
        raise ConfigurationError(f"{field_name}: an expression feature is computed, not read")
    raise ConfigurationError(
        f"field {field_name!r} must start with 'instrument.', 'rollup.', 'market.' or 'feature.'"
    )
