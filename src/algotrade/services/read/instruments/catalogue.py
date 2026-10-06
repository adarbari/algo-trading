"""The feature catalogue a caller reads values by (ADR 0038): one ``FeatureInfo`` per field
(``instrument.<column>``, ``rollup.<group>@v<N>.<column>``, ``feature.<name>``) with its
metadata and the display ``format`` derived here, on the server, from its unit and dtype (the
browser never guesses a format from a feature's name), and, on the catalogue read, the site
field guide's entry for it (``guide``: how to read it, the criterion per intent, caveats; ADR
0041 amended) so the Builder explains a field with the same words the drafting model gets.

The catalogue is the caller's: the site's fields plus their own expression features
(``ctx.features``, read once per request; ADR 0023 step 4). Instrument facts first, then
feature groups in registry order, then expression features. A market's catalogue
(``entity="market"``, ADR 0047) is its groups' ``market.<group>@v<N>.<column>`` fields and
the expression features over them."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Any

from algotrade.config.site.field_guide import (
    FieldGuideEntry,
    FieldGuideSettings,
)
from algotrade.config.site.field_guide import (
    GuideUse as GuideUseEntry,
)
from algotrade.config.site.settings import load_field_guide
from algotrade.core.model.errors import ConfigurationError
from algotrade.core.model.fields import (
    COMPANY_TABLE,
    FEATURE_FIELD_PREFIX,
    GROUP_FIELD_HEADS,
    field_source,
    is_feature_field,
)
from algotrade.features.expressions.feature_set import FeatureSet
from algotrade.services.configs import catalog_of
from algotrade.services.read.context import Stores

INSTRUMENT_NULL = "not known for this instrument (UNKNOWN)"


class FeatureFormat(StrEnum):
    """How a client shows a feature's value (docs/api/read-model.md "GraphQL conventions")."""

    PERCENT = "percent"  # a fraction: 0.25 reads 25%
    CURRENCY = "currency"  # dollars per share or contract: $12.34
    COMPACT = "compact"  # a large amount or count: 13.9B (unit says dollars or shares)
    NUMBER = "number"  # a plain number: counts, sessions, ratios, percentage points
    DATE = "date"
    FLAG = "flag"
    CATEGORY = "category"  # one value of a closed set (a status, tier or class)
    TEXT = "text"


# Numeric units with a format of their own (features.framework.feature.UNITS); other numbers
# (counts, sessions, days, ratios) are NUMBER, and so is ``pct_points`` (25 is 25%): PERCENT
# means a fraction.
_NUMBER_FORMATS = {
    "decimal": FeatureFormat.PERCENT,
    "usd_per_share": FeatureFormat.CURRENCY,
    "usd": FeatureFormat.COMPACT,
    "shares": FeatureFormat.COMPACT,
}


def format_of(dtype: str, unit: str | None) -> FeatureFormat:
    """The display format of a value of ``dtype`` (``core.model.fields.FIELD_TYPES``) in
    ``unit`` (None: no unit declared, e.g. an ``instrument.*`` fact)."""
    if dtype == "date" or unit == "date":
        return FeatureFormat.DATE
    if dtype == "bool" or unit == "flag":
        return FeatureFormat.FLAG
    if dtype == "str":
        return FeatureFormat.CATEGORY if unit == "category" else FeatureFormat.TEXT
    return _NUMBER_FORMATS.get(unit or "", FeatureFormat.NUMBER)


@dataclass(frozen=True)
class GuideUse:
    """One intent a trader has for a field and the criterion that expresses it, as a rule
    screen takes it: ``op``, ``value`` (in the field's unit), ``mode``, ``tolerance`` (a number
    in the unit, or ``{"relative": r}``), ``on_miss`` (soft only), ``note`` on combining it."""

    intent: str
    op: str
    value: Any
    mode: str
    tolerance: float | dict[str, float] | None
    on_miss: str | None
    note: str

    @classmethod
    def from_entry(cls, u: GuideUseEntry) -> "GuideUse":
        tolerance = dict(u.tolerance) if isinstance(u.tolerance, Mapping) else u.tolerance
        return cls(u.intent, u.op, u.value, u.mode, tolerance, u.on_miss or None, u.note)


@dataclass(frozen=True)
class FieldGuide:
    """The site field guide's entry for a field (``docs/data/field-guide.md``): how to read
    it, the criterion per intent, when the reading lies (each caveat names the field that
    exposes it), the sources."""

    theme: str
    reads: str
    uses: tuple[GuideUse, ...]
    caveats: tuple[str, ...]
    sources: tuple[str, ...]

    @classmethod
    def from_entry(cls, e: FieldGuideEntry) -> "FieldGuide":
        return cls(
            e.theme, e.reads, tuple(GuideUse.from_entry(u) for u in e.uses), e.caveats, e.sources
        )


@dataclass(frozen=True)
class FeatureInfo:
    """One catalogue field: what it is, how it is computed and stored, how to show it.
    ``source``: the table it is read from (``expression``: computed on read); ``key``: the
    feature key ``<group>.<column>@v<N>``; ``range``: plausible ``(min, max)`` (values outside
    are kept); ``scope``: ``site`` or ``user`` (one of the caller's own expression features,
    declared by ``owner``); ``licence``: ``open`` or ``personal`` (ADR 0028); ``guide``: the
    site field guide's entry (None: no entry, or a read that did not attach the guide)."""

    name: str
    kind: str
    source: str
    dtype: str
    format: FeatureFormat
    description: str
    null_meaning: str
    version: int | None = None
    group: str | None = None
    key: str | None = None
    inputs: tuple[str, ...] = ()
    unit: str | None = None
    range: tuple[float | None, float | None] | None = None
    categories: tuple[str, ...] = ()
    scope: str = "site"
    owner: str | None = None
    licence: str = "open"
    guide: FieldGuide | None = None


class UnknownFeatureError(ConfigurationError):
    """A name that is not in the caller's catalogue (GraphQL ``UNKNOWN_FEATURE``)."""


def _group_info(fs: FeatureSet, name: str, dtype: str) -> FeatureInfo:
    found = fs.feature(name)
    if found is None:  # pragma: no cover - every catalogue field of a group is declared
        raise UnknownFeatureError(f"no feature metadata for {name!r}")
    unit = found.unit or None
    return FeatureInfo(
        name=name,
        kind=found.kind,
        source=field_source(name)[0],
        dtype=dtype,
        format=format_of(dtype, unit),
        description=found.description,
        null_meaning=found.null_meaning,
        version=found.version,
        group=found.group,
        key=found.key,
        inputs=tuple(found.inputs) or tuple(i.table for i in fs.code[found.group].inputs),
        unit=unit,
        range=found.valid_range,
        categories=tuple(found.categories),
        licence=found.licence,
    )


def _expression_info(fs: FeatureSet, name: str, dtype: str) -> FeatureInfo:
    expression = fs.expressions[name.removeprefix(FEATURE_FIELD_PREFIX)]
    f = expression.feature
    unit = f.unit or None
    return FeatureInfo(
        name=name,
        kind=f.kind,
        # A materialised expression is read from its own table (its one stored input).
        source=next(iter(fs.stored_columns([f.name]))) if expression.materialise else "expression",
        dtype=dtype,
        format=format_of(dtype, unit),
        description=f.description,
        null_meaning=f.null_meaning,
        version=f.version,
        key=f.key,
        inputs=tuple(f.inputs),
        unit=unit,
        range=f.valid_range,
        categories=tuple(f.categories),
        scope=expression.scope,
        owner=expression.definition.owner,
        licence=f.licence,
    )


def _instrument_info(name: str, dtype: str) -> FeatureInfo:
    table, _ = field_source(name)
    kind = "company detail (SEC EDGAR)" if table == COMPANY_TABLE else "reference fact"
    return FeatureInfo(
        name, "instrument", table, dtype, format_of(dtype, None), kind, INSTRUMENT_NULL
    )


def _info(fs: FeatureSet, name: str, dtype: str) -> FeatureInfo:
    if name.partition(".")[0] in GROUP_FIELD_HEADS.values():
        return _group_info(fs, name, dtype)
    if is_feature_field(name):
        return _expression_info(fs, name, dtype)
    return _instrument_info(name, dtype)


def feature_infos(
    fs: FeatureSet,
    names: Sequence[str] | None = None,
    entity: str = "instrument",
    guide: FieldGuideSettings | None = None,
) -> dict[str, FeatureInfo]:
    """The catalogue entries of ``names`` in ``fs`` (None: every field, in catalogue order;
    see the module docstring) for one ``entity``, each with ``guide``'s entry when a guide is
    given. ``UnknownFeatureError`` naming the first name ``fs`` does not have (and where it
    moved, for a field of a superseded group)."""
    if entity != "instrument":
        return _entity_infos(fs, names, entity)
    catalogue = catalog_of(fs)
    out: dict[str, FeatureInfo] = {}
    for name in catalogue.fields if names is None else names:
        if name not in catalogue.fields:
            try:
                catalogue.check_field(name, "features")
            except ConfigurationError as error:
                raise UnknownFeatureError(str(error)) from error
        info = _info(fs, name, catalogue.fields[name])
        entry = guide.entry(name) if guide is not None else None
        out[name] = replace(info, guide=FieldGuide.from_entry(entry)) if entry is not None else info
    return out


def _entity_infos(
    fs: FeatureSet, names: Sequence[str] | None, entity: str
) -> dict[str, FeatureInfo]:
    fields = fs.field_types(entity)
    unknown = [n for n in names or () if n not in fields]
    if unknown:
        raise UnknownFeatureError(f"unknown {entity} feature {unknown[0]!r}")
    return {n: _info(fs, n, fields[n]) for n in (fields if names is None else names)}


def load_catalogue(ctx: Stores) -> tuple[FeatureInfo, ...]:
    """The caller's catalogue (``ctx.features``), in catalogue order, with the site field
    guide's entries (``ctx.configs``)."""
    return tuple(feature_infos(ctx.features, guide=load_field_guide(ctx.configs)).values())
