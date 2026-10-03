"""Which fields a selection may reference, their types, and which table each comes from.

Field names:
- ``instrument.<column>``          L1 reference facts (``instruments/reference``; company
                                   fields such as ``sector`` from ``instruments/company``)
- ``rollup.<name>@v<N>.<column>``  a registered rollup (``rollups/instrument/<name>@v<N>``)
- ``feature.<name>``               an expression feature (computed on read)

A field of a superseded group version (``rollup.price_stats@v1.pct_from_high_52w``) fails
with the field that replaced it (``moved``), so a stale config says what to write instead.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass

from algotrade.config.strategy.schema import NO_VALUE_OPS, Group, Rule
from algotrade.core.model.errors import ConfigurationError
from algotrade.core.model.fields import FIELD_TYPES, REFERENCE_TABLE, field_source

__all__ = ["FIELD_TYPES", "INSTRUMENT_FIELDS", "REFERENCE_TABLE", "FieldCatalog", "field_source"]

INSTRUMENT_FIELDS: Mapping[str, str] = {
    "instrument_id": "str",
    "symbol": "str",
    "name": "str",
    "asset_class": "str",
    "security_type": "str",
    "exchange": "str",
    "currency": "str",
    "multiplier": "float",
    "tick_size": "float",
    "is_etf": "bool",
    "is_leveraged": "bool",
    "is_inverse": "bool",
    "leverage": "float",
    "tracks": "str",
    "optionable": "bool",
    "status": "str",
    "listed_on": "date",
    "delisted_on": "date",
    "first_seen": "date",
    "round_lot": "float",
    "is_test_issue": "bool",
    "financial_status": "str",
    "in_sp500": "bool",
    # SEC EDGAR company details (instruments/company)
    "sic": "str",
    "sic_description": "str",
    "sic_division": "str",
    "sector": "str",
    "industry": "str",
    "state_of_incorporation": "str",
    "fiscal_year_end": "str",
    "website": "str",
}


@dataclass(frozen=True)
class FieldCatalog:
    fields: Mapping[str, str]  # field name -> type
    # A stale field -> the field that replaced it ("": retired), else None.
    moved: Callable[[str], str | None] | None = None

    @classmethod
    def build(
        cls,
        rollups: Mapping[str, Mapping[str, str]],
        features: Mapping[str, str] | None = None,
        moved: Callable[[str], str | None] | None = None,
    ) -> "FieldCatalog":
        """``rollups``: ``{"option_liquidity@v1": {"put_tier": "str", ...}}``; ``features``:
        expression features by name -> type (``feature.<name>``)."""
        fields = {f"instrument.{c}": t for c, t in INSTRUMENT_FIELDS.items()}
        for rollup, columns in rollups.items():
            fields.update({f"rollup.{rollup}.{c}": t for c, t in columns.items()})
        fields.update({f"feature.{n}": t for n, t in (features or {}).items()})
        bad = sorted(t for t in fields.values() if t not in FIELD_TYPES)
        if bad:
            raise ConfigurationError(f"unknown field types {bad}")
        return cls(fields, moved)

    def check(self, group: Group, path: str = "selection") -> None:
        for rule in group.rules():
            self._check_rule(rule, path)

    def check_field(self, field_name: str, path: str) -> str:
        if field_name not in self.fields:
            now = self.moved(field_name) if self.moved is not None else None
            if now is not None:
                instead = f"use {now!r}" if now else "it was retired with no replacement"
                raise ConfigurationError(
                    f"{path}: field {field_name!r} is from a superseded feature group: "
                    f"{instead} (ADR 0023 step 3, docs/configuration.md)"
                )
            raise ConfigurationError(f"{path}: unknown field {field_name!r}")
        return self.fields[field_name]

    def _check_rule(self, rule: Rule, path: str) -> None:
        kind = self.check_field(rule.field, path)
        if rule.op in NO_VALUE_OPS:
            return
        values = rule.value if isinstance(rule.value, tuple) else (rule.value,)
        numeric_op = rule.op in ("gt", "gte", "lt", "lte", "between")
        for value in values:
            ok = {
                "bool": isinstance(value, bool),
                "str": isinstance(value, str),
                "date": isinstance(value, str),
                "float": isinstance(value, (int, float)) and not isinstance(value, bool),
                "float32": isinstance(value, (int, float)) and not isinstance(value, bool),
                "int": isinstance(value, int) and not isinstance(value, bool),
            }[kind]
            if not ok or (numeric_op and kind == "bool"):
                raise ConfigurationError(
                    f"{path}: {rule.describe()} does not fit field type {kind!r}"
                )
