"""The ``Feature`` declaration: one named, typed, documented column of a feature group.

A feature is what a selection, a screener or a report reads: ``<group>.<column>@v<N>``
(selectable as ``rollup.<group>@v<N>.<column>``), or a site expression feature
``<name>@v<N>`` with no group (``config/site/features/*.toml``; selectable as
``feature.<name>``, computed on read unless materialised: ``features.expressions``). Its
metadata is declared next to the compute that produces it (``features/rollups/<group>.py``)
and drives the generated feature catalogue (``docs/data/features.md``), the stored column
type and, later, UI and email labels (ADR 0023).

- ``entity``      what one row describes: ``instrument`` (one row per instrument) or
                  ``market`` (one ``MKT:US`` row per session: breadth, trend, regime; stored
                  in ``rollups/market/``, selectable as ``market.<group>@v<N>.<column>``;
                  ADR 0047). A group's value is inherited by its features; an expression
                  feature's is that of what it reads (mixing entities is an error).
                  ``contract`` and ``sector`` are reserved for when a feature needs that grain
- ``kind``        how it is computed: ``window`` (one entity's history up to the session:
                  bars, events, filings, earlier sessions), ``chain`` (one session's option
                  chain), ``expression`` (arithmetic / logic over other features of the same
                  row), ``cross_section`` (across entities on one session), ``label`` (a
                  status, tier or class from a fixed rule)
- ``dtype``       the stored type (``core.model.fields.FIELD_TYPES``)
- ``unit``        ``UNITS``: ``decimal`` is a fraction (0.25 = 25%), ``pct_points`` is 25 =
                  25%, ``ratio`` a plain quotient, ``sessions`` exchange sessions, ``days``
                  calendar days
- ``null_meaning``  why the value can be null (null is UNKNOWN, never zero)
- ``valid_range`` plausible ``(min, max)`` (``None``: open); values outside are kept, not
                  clipped: a range is a sanity bound for checks, not a filter
- ``categories``  the closed set of values of a label (empty: open, e.g. a free-text status)
- ``inputs``      what it is computed from: other features (``<group>.<column>@v<N>``, an
                  expression feature ``<name>@v<N>``) or raw fields (``<table>.<column>``,
                  e.g. ``bars/1d.close``)
- ``licence``     who may see its values: ``open`` (our own computation from free data) or
                  ``personal`` (derived from a personal-use market-data licence, e.g. IBKR's:
                  shown to the owner only once there are other users; ADR 0028). An
                  expression feature takes the most restrictive licence of its inputs
- ``applies_to``  which instruments the feature is defined for: ``any``, ``optionable``
                  (option-chain features: a non-optionable instrument has none) or
                  ``operating_company`` (earnings: only a common stock or ADR that is not a
                  blank-check company, SEC SIC 6770; ADR 0045). A group's value is inherited by its
                  features.
                  Where it does not apply the read says NOT_APPLICABLE, not UNKNOWN (ADR 0042)
- ``null_status`` the status column saying why this one is null: a sibling column of the same
                  group (``iv30_status``) or another group's (``iv30.iv30_status@v1``, for a
                  feature derived from it); when its value is an illiquid status the read
                  says ILLIQUID (ADR 0042), when it is an explained one EXPLAINED (ADR 0046)
- ``illiquid_statuses``  which ``null_status`` values mean the chain is too thin
- ``explained_statuses``  which ``null_status`` values explain the null in words a reader
                  acts on; each is a ``NullReason`` value and the status value is the reason
                  (``bar_status`` ``NO_TRADE``: "No trade"). Other values stay NULL. A
                  ``null_status`` needs at least one of the two lists, and either list needs it
- ``version``     the feature's definition version: a group feature's is its group's (a
                  group is re-versioned only when its stored columns change); an expression
                  feature's is its own
"""

import re
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

from algotrade.core.model.fields import FIELD_TYPES, NUMERIC_TYPES, group_field, rollup_table

type Entity = Literal["instrument", "market"]
type Kind = Literal["window", "chain", "expression", "cross_section", "label"]
type Range = tuple[float | None, float | None]
type Licence = Literal["open", "personal"]
type AppliesTo = Literal["any", "optionable", "operating_company"]
# A status field, the values of it that read ILLIQUID and those that read EXPLAINED, and the
# stored table of the feature declaring it (an EXPLAINED status covers a missing row there only).
type StatusRule = tuple[str, frozenset[str], frozenset[str], str]

ENTITIES = frozenset({"instrument", "market"})
KINDS = frozenset({"window", "chain", "expression", "cross_section", "label"})
LICENCES = ("open", "personal")  # least to most restrictive
APPLIES_TO = ("any", "optionable", "operating_company")
UNITS = frozenset(
    {
        "decimal",  # a fraction: 0.25 is 25% (returns, vols, yields, rates, relative spreads)
        "pct_points",  # a percentage as quoted: 25 is 25%
        "ratio",  # a plain quotient (iv / hv), or a dimensionless sensitivity (delta)
        "usd",  # US dollars (dollar volume, market cap)
        "usd_per_share",  # a price per share or per option contract unit
        "shares",  # a share count
        "count",  # how many of something (contracts, ex-dates, quotes)
        "sessions",  # exchange sessions (core.time.calendar)
        "days",  # calendar days
        "date",  # a calendar date
        "flag",  # true / false
        "category",  # one value of a set (a status, tier or class)
        "text",  # an identifier or free text
    }
)


class NullReason(StrEnum):
    """Why a value is null when the data is complete and the null itself is the fact (ADR
    0046): a closed set, so every client can label each one. A status column whose value
    explains a null holds one of these names."""

    NO_TRADE = "NO_TRADE"  # no bar on the session: the instrument did not trade
    NOT_ANNOUNCED = "NOT_ANNOUNCED"  # the company has not announced its next report date
    NEW_LISTING = "NEW_LISTING"  # too few sessions since listing for the window
    FEW_BARS = "FEW_BARS"  # trades too rarely to fill the window


_NAME = re.compile(r"^[a-z][a-z0-9_]*$")
_FEATURE_REF = re.compile(r"^([a-z][a-z0-9_]*\.)?[a-z][a-z0-9_]*@v[1-9][0-9]*$")
_RAW_REF = re.compile(r"^[a-z0-9_/]+\.[a-z][a-z0-9_]*$")
SERIES_REF = "series:"  # a macro series or index level by its macro.toml key (ADR 0048)
_SERIES_REF = re.compile(r"^series:[A-Z0-9][A-Z0-9_]*$")


@dataclass(frozen=True)
class Feature:
    name: str  # the stored column
    dtype: str
    unit: str
    description: str
    null_meaning: str
    kind: Kind = "window"
    valid_range: Range | None = None
    categories: tuple[str, ...] = ()
    inputs: tuple[str, ...] = ()
    entity: Entity = "instrument"
    version: int = 0  # 0: the group's version (set when the group is declared)
    group: str = ""  # the owning group's key (set when declared); "": an expression feature
    licence: Licence = "open"
    applies_to: AppliesTo = "any"
    null_status: str = ""  # a sibling status column; "": null always means UNKNOWN
    illiquid_statuses: tuple[str, ...] = ()  # the null_status values that mean "too thin"
    explained_statuses: tuple[str, ...] = ()  # the null_status values that are a NullReason

    @property
    def key(self) -> str:
        """``<group>.<column>@v<N>`` (columns repeat across groups, so the name is
        qualified), or ``<name>@v<N>`` for an expression feature (names are unique)."""
        if not self.group:
            return f"{self.name}@v{self.version}"
        return f"{self.group.partition('@')[0]}.{self.name}@v{self.version}"

    @property
    def status_column(self) -> tuple[str, str]:
        """Where ``null_status`` lives: (the group key ``<group>@v<N>``, the column); ``("",
        "")`` when there is none. A sibling column is in this feature's own group."""
        if not self.null_status:
            return "", ""
        if "@" not in self.null_status:
            return self.group, self.null_status
        group, _, rest = self.null_status.partition(".")
        column, _, version = rest.partition("@")
        return f"{group}@{version}", column

    @property
    def status_table(self) -> str:
        """The stored table holding ``null_status`` (``""``: none)."""
        group, _ = self.status_column
        return rollup_table(self.entity, group) if group else ""

    @property
    def status_field(self) -> str:
        """The selection field of ``null_status`` (``""``: none): a sibling column of this
        group, or ``<group>.<column>@v<N>`` of another."""
        group, column = self.status_column
        return group_field(self.entity, group, column) if group else ""

    @property
    def field(self) -> str:
        """The selection field: ``rollup.<group>@v<N>.<column>`` (``market.`` for a market
        group) or ``feature.<name>``."""
        if not self.group:
            return f"feature.{self.name}"
        return group_field(self.entity, self.group, self.name)


def is_feature_ref(ref: str) -> bool:
    """``<group>.<column>@v<N>`` or ``<name>@v<N>`` (otherwise a raw field
    ``<table>.<column>``)."""
    return bool(_FEATURE_REF.match(ref))


def is_series_ref(ref: str) -> bool:
    """``series:<KEY>``: a ``macro/series`` series named by its ``macro.toml`` key."""
    return bool(_SERIES_REF.match(ref))


def feature_problems(feature: Feature) -> list[str]:
    """Why a feature declaration is invalid (empty: valid)."""
    f = feature
    problems = []
    if not _NAME.match(f.name):
        problems.append(f"{f.name}: name must match {_NAME.pattern}")
    if f.dtype not in FIELD_TYPES:
        problems.append(f"{f.name}: dtype must be one of {sorted(FIELD_TYPES)}")
    if f.unit not in UNITS:
        problems.append(f"{f.name}: unit {f.unit!r} must be one of {sorted(UNITS)}")
    if f.kind not in KINDS:
        problems.append(f"{f.name}: kind {f.kind!r} must be one of {sorted(KINDS)}")
    if f.entity not in ENTITIES:
        problems.append(f"{f.name}: entity {f.entity!r} must be one of {sorted(ENTITIES)}")
    if f.licence not in LICENCES:
        problems.append(f"{f.name}: licence {f.licence!r} must be one of {list(LICENCES)}")
    problems += _absence_problems(f)
    if not f.description.strip() or not f.null_meaning.strip():
        problems.append(f"{f.name}: describe it and say when it is null")
    if f.valid_range is not None:
        lo, hi = f.valid_range
        if f.dtype not in NUMERIC_TYPES:
            problems.append(f"{f.name}: a valid_range needs a numeric dtype")
        elif lo is not None and hi is not None and lo > hi:
            problems.append(f"{f.name}: valid_range min > max")
    if f.categories and f.dtype != "str":
        problems.append(f"{f.name}: categories need dtype str")
    refs = (is_feature_ref, _RAW_REF.match, is_series_ref)
    bad = [r for r in f.inputs if not any(ok(r) for ok in refs)]
    if bad:
        problems.append(
            f"{f.name}: inputs {bad} are neither <group>.<column>@vN, table.column nor series:<KEY>"
        )
    return problems


def _absence_problems(f: Feature) -> list[str]:
    problems = []
    if f.applies_to not in APPLIES_TO:
        problems.append(f"{f.name}: applies_to {f.applies_to!r} must be one of {list(APPLIES_TO)}")
    if "@" in f.null_status and not is_feature_ref(f.null_status):
        problems.append(f"{f.name}: null_status {f.null_status!r} is not <group>.<column>@vN")
    if bool(f.null_status) != bool(f.illiquid_statuses or f.explained_statuses):
        problems.append(f"{f.name}: null_status goes with illiquid_statuses or explained_statuses")
    bad = sorted(set(f.explained_statuses) - set(NullReason))
    if bad:
        problems.append(f"{f.name}: explained_statuses {bad} are not NullReason values")
    if set(f.explained_statuses) & set(f.illiquid_statuses):
        problems.append(f"{f.name}: a status is either illiquid or explained, not both")
    return problems


OPERATING_TYPES = frozenset({"COMMON_STOCK", "ADR"})  # security types that can report earnings
BLANK_CHECK_SIC = "6770"  # SEC SIC code of a blank-check company (SPAC): no operations


def not_applicable(
    applies: Iterable[str],
    optionable: bool | None,
    security_type: str | None,
    sic: str | None = None,
) -> str:
    """The ``applies_to`` value that rules a feature out for an instrument with these
    reference and company facts, or ``""`` when it applies (ADR 0042, ADR 0045). A null fact
    never rules out: a null ``optionable``, ``security_type`` or ``sic`` is unknown, not "no".
    The one decision: the read layer (NOT_APPLICABLE) and the nightly coverage check share it."""
    wanted = set(applies)
    if "optionable" in wanted and optionable is False:
        return "optionable"
    if "operating_company" in wanted:
        if security_type and security_type not in OPERATING_TYPES:
            return "operating_company"
        if (sic or "").strip() == BLANK_CHECK_SIC:
            return "operating_company"
    return ""


def strictest(licences: Iterable[str]) -> Licence:
    """The most restrictive of ``licences`` (``open`` when there are none)."""
    found = [LICENCES.index(x) for x in licences if x in LICENCES]
    return "personal" if found and max(found) == 1 else "open"


def in_range(feature: Feature, value: float) -> bool:
    """Whether a non-null ``value`` is inside the feature's ``valid_range`` (open: True)."""
    if feature.valid_range is None:
        return True
    lo, hi = feature.valid_range
    return (lo is None or value >= lo) and (hi is None or value <= hi)
