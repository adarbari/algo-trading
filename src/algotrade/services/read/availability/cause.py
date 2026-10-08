"""The vocabulary of "not available" (ADR 0056): the public ``UnavailableKind`` with its
generic wording and Guide term, the admin-only ``Cause`` chain made of ``CauseLink`` s, and
``Unavailable`` (a kind, the features it hides, its cause).

A construction site builds the leaf it knows (``table_cause``: a table with no partition or
no row for the session); ``explain.explain`` expands it upstream from stored run records. The
kind comes from the code and from whether a failure stands behind the table
(``ReadContext.kind_of``: a step that did not SUCCEED, a table with no partition, or a group
reading one is SYSTEM; a gap with none is NOT_STORED), never from the chain itself, so a
trader's read never pays for (or leaks) the chain."""

from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum
from typing import Any

__all__ = [
    "ADMIN_CAUSE",
    "AUDIT",
    "GENERIC",
    "GENERIC_REASONS",
    "GUIDE_TERMS",
    "TABLE_PREFIXES",
    "Cause",
    "CauseLevel",
    "CauseLink",
    "Unavailable",
    "UnavailableKind",
    "feature_cause",
    "names_a_table",
    "public_audit",
    "run_cause",
    "table_cause",
]


# A REST field that carries a cause says so in its schema (pydantic ``json_schema_extra``, or a
# dataclass field's ``metadata``) with this key; its value is what anyone but an admin gets
# instead: ``None``, ``[]`` or ``GENERIC`` (the generic words, for a text). ``redact`` applies
# it; ``tests/architecture/api/test_rest_causes.py`` finds every such field.
ADMIN_CAUSE = "admin_cause"
GENERIC = "generic"
AUDIT = "audit"  # a stored audit document: ``public_audit`` drops the keys that name tables
AUDIT_CAUSE_KEYS = frozenset({"missing_tables", "missing_optional_tables"})


class UnavailableKind(StrEnum):
    """The public reason class of a gap: all a trader is told (the Guide term explains it)."""

    SYSTEM = "SYSTEM"  # a real failure: a source down, a step failed, a table missing
    NOT_STORED = "NOT_STORED"  # no row / a stored null, with no failure behind it
    NOT_APPLICABLE = "NOT_APPLICABLE"  # not defined for this instrument (or the null is a fact)
    ILLIQUID = "ILLIQUID"  # an option value null because the chain is too thin
    LICENCE = "LICENCE"  # a personal-licence feature and the caller is not its owner
    NOT_RUN = "NOT_RUN"  # a screener (or check) has no run for the session


# What a trader reads: never a table, vendor, step or error text.
GENERIC_REASONS: dict[UnavailableKind, str] = {
    UnavailableKind.SYSTEM: "not available because of a system error",
    UnavailableKind.NOT_STORED: "not available for this instrument",
    UnavailableKind.NOT_APPLICABLE: "does not apply to this instrument",
    UnavailableKind.ILLIQUID: "not available: too thinly traded today",
    UnavailableKind.LICENCE: "not available under your data licence",
    UnavailableKind.NOT_RUN: "not run for this session",
}

# The Guide glossary term (config/site/guide/glossary.toml) that explains each kind; the
# fitness test ``test_every_kind_has_a_glossary_term`` keeps this complete.
GUIDE_TERMS: dict[UnavailableKind, str] = {
    UnavailableKind.SYSTEM: "unavailable_system",
    UnavailableKind.NOT_STORED: "unavailable_not_stored",
    UnavailableKind.NOT_APPLICABLE: "unavailable_not_applicable",
    UnavailableKind.ILLIQUID: "unavailable_illiquid",
    UnavailableKind.LICENCE: "unavailable_licence",
    UnavailableKind.NOT_RUN: "not_run",
}

# A stored table's path starts with one of these: text that has one names storage.
TABLE_PREFIXES = ("rollups/", "bars/", "chains/", "volatility/", "results/", "instruments/")


def public_audit(value: Any) -> Any:
    """``value`` (a run record's or a selection's audit document) without the keys that name the
    tables a run went without, at any depth: the trader's copy of an audit."""
    if isinstance(value, dict):
        return {k: public_audit(v) for k, v in value.items() if k not in AUDIT_CAUSE_KEYS}
    if isinstance(value, list):
        return [public_audit(v) for v in value]
    return value


def names_a_table(text: str) -> bool:
    """Whether ``text`` names a stored table (what a trader's text must never do)."""
    return any(prefix in text for prefix in TABLE_PREFIXES)


class CauseLevel(StrEnum):
    """What one link of a chain is, root first: SOURCE -> STEP -> TABLE -> FEATURE (a RUN
    stands alone: a screener with no run for the session)."""

    SOURCE = "SOURCE"
    STEP = "STEP"
    TABLE = "TABLE"
    FEATURE = "FEATURE"
    RUN = "RUN"


@dataclass(frozen=True)
class CauseLink:
    """One link: ``subject`` is the thing (a step name, a table, a feature), ``status`` its
    state as recorded (``FAILED``, ``NO_PARTITION``), ``message`` the stored words; ``run_id``
    the run record it came from and ``session`` the session it is about, when known."""

    level: CauseLevel
    subject: str
    status: str
    message: str
    run_id: str | None = None
    session: date | None = None


@dataclass(frozen=True)
class Cause:
    """A chain of links ordered root cause first, leaf last. Admin-only: the server serves it
    through ``AdminCause`` (GraphQL) or ``redact`` (REST), never to a trader."""

    links: tuple[CauseLink, ...]

    @property
    def leaf(self) -> CauseLink:
        return self.links[-1]

    @property
    def text(self) -> str:
        """The messages root first, joined: what an admin's flat ``detail`` reads."""
        return " -> ".join(link.message for link in self.links if link.message)

    def first(self, level: CauseLevel) -> CauseLink | None:
        """The first link of ``level`` (None: the chain has none)."""
        return next((link for link in self.links if link.level is level), None)


def table_cause(
    table: str, message: str, status: str = "NO_PARTITION", session: date | None = None
) -> Cause:
    """The leaf of a table with nothing for the session, as the construction site knows it."""
    return Cause((CauseLink(CauseLevel.TABLE, table, status, message, session=session),))


def feature_cause(feature: str, message: str, status: str, session: date | None = None) -> Cause:
    """The leaf of a value null for a reason about the feature itself (not applicable, too
    thin, a stored null, an explained null), as the construction site knows it."""
    return Cause((CauseLink(CauseLevel.FEATURE, feature, status, message, session=session),))


def run_cause(run: str, message: str, session: date | None = None) -> Cause:
    """The leaf of a screener or check with no run for the session."""
    return Cause((CauseLink(CauseLevel.RUN, run, "NOT_RUN", message, session=session),))


@dataclass(frozen=True)
class Unavailable:
    """A set of features a page cannot show, why in public words (``kind``) and, for an admin,
    the chain (``cause``); ``guide_term`` is the glossary entry that explains the kind."""

    kind: UnavailableKind
    features: tuple[str, ...]
    cause: Cause
    guide_term: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "guide_term", GUIDE_TERMS[self.kind])

    @property
    def reason(self) -> str:
        return GENERIC_REASONS[self.kind]
