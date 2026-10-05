"""Field names for instrument-level data, shared by configs (selections) and storage (views).

- ``instrument.<column>``          L1 reference facts (``instruments/reference``); company
                                   columns (``COMPANY_FIELDS``) come from ``instruments/company``
- ``rollup.<name>@v<N>.<column>``  a rollup (``rollups/instrument/<name>@v<N>``)
- ``feature.<name>``               an expression feature (``config/site/features/*.toml``),
                                   computed on read from the stored features it names
"""

from algotrade.core.model.errors import ConfigurationError

REFERENCE_TABLE = "instruments/reference"
COMPANY_TABLE = "instruments/company"
DESCRIPTION_TABLE = "instruments/description"  # what a company or fund is about (ADR 0034)
ROLLUP_TABLE_PREFIX = "rollups/instrument/"
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


def is_feature_field(field_name: str) -> bool:
    """``feature.<name>``: an expression feature, computed on read (no table of its own)."""
    return field_name.startswith(FEATURE_FIELD_PREFIX)


def field_source(field_name: str) -> tuple[str, str]:
    """``(table, column)`` a field is read from (not for ``feature.<name>``: computed)."""
    head, _, rest = field_name.partition(".")
    if head == "instrument" and rest:
        return (COMPANY_TABLE if rest in COMPANY_FIELDS else REFERENCE_TABLE), rest
    if head == "rollup" and "." in rest:
        rollup, _, column = rest.rpartition(".")
        return f"{ROLLUP_TABLE_PREFIX}{rollup}", column
    if head == "feature":
        raise ConfigurationError(f"{field_name}: an expression feature is computed, not read")
    raise ConfigurationError(
        f"field {field_name!r} must start with 'instrument.', 'rollup.' or 'feature.'"
    )
