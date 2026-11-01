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
from dataclasses import dataclass, field

from algotrade.config.strategy.levels import (
    LEVELS,
    OPEN_ONLY_SITES,
    SCREENER,
    STRICT_SITES,
    Level,
    levels_at,
)
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


STRING_OPS_NEEDING_DOMAIN = ("ne", "not_in")  # TRUE on a value we never saw, unless read as missing
NULL_TESTS = ("is_null", "not_null")  # TRUE or FALSE on a gap: refused where missing never passes


@dataclass(frozen=True)
class FieldCatalog:
    """The fields a rule may name. ``fields`` is the instrument level (selections and rule
    screens, today's meaning); ``levels`` the other levels' fields by level key (``market``, the
    computed ``position`` fields the edge loader passes in, ...); ``check(site=...)`` reads the
    levels ``LEVELS`` lets that site name. ``licences`` maps a field to its licence (an
    expression takes the strictest of its inputs); ``domains`` a string field to its declared
    values."""

    fields: Mapping[str, str]  # instrument field name -> type
    # A stale field -> the field that replaced it ("": retired), else None.
    moved: Callable[[str], str | None] | None = None
    levels: Mapping[str, Mapping[str, str]] = field(default_factory=dict)
    licences: Mapping[str, str] = field(default_factory=dict)
    domains: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    declared: tuple[Level, ...] = LEVELS  # the levels table (a test may declare its own)

    @classmethod
    def build(
        cls,
        rollups: Mapping[str, Mapping[str, str]],
        features: Mapping[str, str] | None = None,
        moved: Callable[[str], str | None] | None = None,
        *,
        levels: Mapping[str, Mapping[str, str]] | None = None,
        licences: Mapping[str, str] | None = None,
        domains: Mapping[str, tuple[str, ...]] | None = None,
        declared: tuple[Level, ...] = LEVELS,
    ) -> "FieldCatalog":
        """``rollups``: ``{"option_liquidity@v1": {"put_tier": "str", ...}}``; ``features``:
        instrument expression features by name -> type (``feature.<name>``); ``levels``: the
        fields of the other levels by level key (``{"market": {"market.vix@v1.close": "float"}}``;
        a level named here must be declared in ``LEVELS``)."""
        fields = {f"instrument.{c}": t for c, t in INSTRUMENT_FIELDS.items()}
        for rollup, columns in rollups.items():
            fields.update({f"rollup.{rollup}.{c}": t for c, t in columns.items()})
        fields.update({f"feature.{n}": t for n, t in (features or {}).items()})
        unknown = sorted(set(levels or {}) - {level.key for level in declared})
        if unknown:
            raise ConfigurationError(
                f"fields of undeclared levels {unknown} (config/strategy/levels.py)"
            )
        heads = {level.key: level.heads for level in declared}
        for key, named in (levels or {}).items():
            stray = [f for f in named if f.partition(".")[0] not in (*heads[key], "feature")]
            if stray:
                raise ConfigurationError(
                    f"{key}-level fields {stray[:3]} do not start with a head of the level "
                    f"{list(heads[key])} (config/strategy/levels.py)"
                )
        everything = [fields, *(levels or {}).values()]
        bad = sorted({t for group in everything for t in group.values() if t not in FIELD_TYPES})
        if bad:
            raise ConfigurationError(f"unknown field types {bad}")
        return cls(
            fields, moved, dict(levels or {}), dict(licences or {}), dict(domains or {}), declared
        )

    def fields_at(self, site: str) -> dict[str, str]:
        """Every field a rule at ``site`` may name (the levels ``LEVELS`` gives it)."""
        found: dict[str, str] = {}
        for level in levels_at(site, self.declared):
            found.update(
                self.fields if level.key == "instrument" else self.levels.get(level.key, {})
            )
        return found

    def level_of(self, field_name: str) -> str | None:
        """The level a field belongs to (None: unknown)."""
        if field_name in self.fields:
            return "instrument"
        return next((k for k, f in self.levels.items() if field_name in f), None)

    def domain_read(self, field_name: str, value: object) -> object:
        """``value`` of a string field read for a strict site: a value outside its declared
        domain is missing (None), so ``ne`` / ``not_in`` on a new label is UNKNOWN, never TRUE.
        A field with no declared domain is returned as it is."""
        domain = self.domains.get(field_name)
        return None if domain is not None and value not in domain else value

    def check(self, group: Group, path: str = "selection", site: str = SCREENER) -> None:
        """Every rule of ``group`` names a field of a level ``site`` may read, and (at a strict
        site) is fail closed: no null test, ``ne`` / ``not_in`` on a string only over a declared
        domain; at the gate every field is openly licensed. The default site is today's
        instrument-only check."""
        for rule in group.rules():
            self._check_rule(rule, path, site)

    def check_field(self, field_name: str, path: str, site: str = SCREENER) -> str:
        allowed = self.fields_at(site)
        if field_name not in allowed:
            level = self.level_of(field_name)
            if level is not None:
                raise ConfigurationError(
                    f"{path}: field {field_name!r} is a {level}-level field, which a rule at "
                    f"the {site!r} site may not name (config/strategy/levels.py)"
                )
            now = self.moved(field_name) if self.moved is not None else None
            if now is not None:
                instead = f"use {now!r}" if now else "it was retired with no replacement"
                raise ConfigurationError(
                    f"{path}: field {field_name!r} is from a superseded feature group: "
                    f"{instead} (ADR 0023 step 3, docs/configuration.md)"
                )
            raise ConfigurationError(f"{path}: unknown field {field_name!r}")
        return allowed[field_name]

    def _check_strict(self, rule: Rule, kind: str, path: str, site: str) -> None:
        if rule.op in NULL_TESTS:
            raise ConfigurationError(
                f"{path}: {rule.describe()}: a rule at the {site!r} site is never null-tested "
                f"(missing data must not pass)"
            )
        if (
            kind == "str"
            and rule.op in STRING_OPS_NEEDING_DOMAIN
            and rule.field not in self.domains
        ):
            raise ConfigurationError(
                f"{path}: {rule.describe()}: {rule.op} on a string field needs a declared domain "
                f"({rule.field!r} has none); use eq or in"
            )
        if site in OPEN_ONLY_SITES and self.licences.get(rule.field) != "open":
            given = self.licences.get(rule.field)
            why = "has no declared licence" if given is None else f"is {given}-licensed"
            raise ConfigurationError(
                f"{path}: field {rule.field!r} {why}; a rule at the {site!r} site reads only "
                f"openly licensed data"
            )
        domain = self.domains.get(rule.field)
        if kind == "str" and domain is not None and rule.op not in NO_VALUE_OPS:
            values = rule.value if isinstance(rule.value, tuple) else (rule.value,)
            outside = [v for v in values if v not in domain]
            if outside:
                raise ConfigurationError(
                    f"{path}: {rule.describe()}: {outside} is not a value of {rule.field!r} "
                    f"(declared: {list(domain)}); a misspelt label would decide the rule"
                )

    def _check_rule(self, rule: Rule, path: str, site: str = SCREENER) -> None:
        kind = self.check_field(rule.field, path, site)
        if site in STRICT_SITES:
            self._check_strict(rule, kind, path, site)
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
