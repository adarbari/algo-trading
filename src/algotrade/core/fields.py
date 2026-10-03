"""Field names for instrument-level data, shared by configs (selections) and storage (views).

- ``instrument.<column>``          L1 reference facts (``instruments/reference``); company
                                   columns (``COMPANY_FIELDS``) come from ``instruments/company``
- ``rollup.<name>@v<N>.<column>``  a rollup (``rollups/instrument/<name>@v<N>``)
"""

from algotrade.core.errors import ConfigurationError

REFERENCE_TABLE = "instruments/reference"
COMPANY_TABLE = "instruments/company"
ROLLUP_TABLE_PREFIX = "rollups/instrument/"
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


def field_source(field_name: str) -> tuple[str, str]:
    """``(table, column)`` a field is read from."""
    head, _, rest = field_name.partition(".")
    if head == "instrument" and rest:
        return (COMPANY_TABLE if rest in COMPANY_FIELDS else REFERENCE_TABLE), rest
    if head == "rollup" and "." in rest:
        rollup, _, column = rest.rpartition(".")
        return f"{ROLLUP_TABLE_PREFIX}{rollup}", column
    raise ConfigurationError(f"field {field_name!r} must start with 'instrument.' or 'rollup.'")
