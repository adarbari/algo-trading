"""Field names for instrument-level data, shared by configs (selections) and storage (views).

- ``instrument.<column>``          L1 reference facts (``instruments/reference``)
- ``rollup.<name>@v<N>.<column>``  a rollup (``rollups/instrument/<name>@v<N>``)
"""

from algotrade.core.errors import ConfigurationError

REFERENCE_TABLE = "instruments/reference"
ROLLUP_TABLE_PREFIX = "rollups/instrument/"


def instrument_field(column: str) -> str:
    return f"instrument.{column}"


def rollup_field(rollup: str, column: str) -> str:
    """``rollup`` is ``<name>@v<N>``."""
    return f"rollup.{rollup}.{column}"


def field_source(field_name: str) -> tuple[str, str]:
    """``(table, column)`` a field is read from."""
    head, _, rest = field_name.partition(".")
    if head == "instrument" and rest:
        return REFERENCE_TABLE, rest
    if head == "rollup" and "." in rest:
        rollup, _, column = rest.rpartition(".")
        return f"{ROLLUP_TABLE_PREFIX}{rollup}", column
    raise ConfigurationError(f"field {field_name!r} must start with 'instrument.' or 'rollup.'")
