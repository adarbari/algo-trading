"""Rules inside an outcome (ADR 0088, design 2.4, 2.4a, 2.13): the canonical form of a rule group
(so a reordered group has one identity), ``[outcome.entry]`` (``when``, ``within_sessions``), and
case values: a parameter that is a literal or ``{ cases = [{ when, value }], default }``. A case
table is split from the outcome before it is typed: the outcome keeps the ``default`` as its
literal (so every reader sees a concrete value) and the cases ride in ``PositionSpec.cases``.
``engines/selection/cases.py::resolve_case`` picks the value at a session. Parse only: the
catalogue check of each rule's fields is ``check_rules`` in ``spec.py``."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, NoReturn, cast

from algotrade.config.edges.positions.grid import BOUNDS, INTEGER_AXES
from algotrade.config.site.fields import Table
from algotrade.config.strategy.schema import Group, parse_group
from algotrade.core.model.errors import ConfigurationError
from algotrade.core.model.ids import validate_id

EXPIRY_CYCLES = ("monthly", "weekly", "any")
CASE_NAMES = ("position", "strike_delta", "tenor_days", "expiry_cycle")
EXIT_CASE_NAMES = ("take_profit", "stop_loss", "exit_dte")
MAX_WAIT_SESSIONS = 20
type Scalar = str | int | float


@dataclass(frozen=True)
class Case:
    when: Group
    value: Scalar


@dataclass(frozen=True)
class CaseValue:
    """A parameter chosen by rule at the decision session: the first case whose rule is TRUE
    gives its value; ``default`` only when every case is FALSE; an UNKNOWN case first makes the
    name unselectable (missing data never chooses a branch)."""

    name: str
    cases: tuple[Case, ...]
    default: Scalar


@dataclass(frozen=True)
class EntrySpec:
    """``[outcome.entry]``: at each close from D to D + ``within_sessions`` - 1 the first one on
    which ``when`` is TRUE is t; S = t + ``start_offset_sessions``; never TRUE: not entered."""

    when: Group
    within_sessions: int = 1


def canonical(group: Group) -> Group:
    """``group`` with the children of every ``all`` / ``any`` in a fixed order (by their text),
    so two spellings of one rule hash the same; the logic is order-free."""
    kids = tuple(canonical(c) if isinstance(c, Group) else c for c in group.children)
    if group.kind != "not":
        kids = tuple(sorted(kids, key=repr))
    return Group(group.kind, kids)


def when_of(raw: object, where: str) -> Group:
    if not isinstance(raw, Mapping):
        raise ConfigurationError(f"{where}: expected a rule table (all / any / not), got {raw!r}")
    return canonical(parse_group(raw, where))


def entry_of(o: Table) -> EntrySpec | None:
    if "entry" not in o.names():
        return None
    t = o.table("entry", ("when", "within_sessions"))
    if "when" not in t.names():
        raise ConfigurationError(f"{t.where} when: required")
    wait = t.integer("within_sessions", 1, 1)
    if wait > MAX_WAIT_SESSIONS:
        raise ConfigurationError(f"{t.where} within_sessions: at most {MAX_WAIT_SESSIONS}")
    return EntrySpec(when_of(t.raw("when"), f"{t.where} when"), wait)


def _literal(name: str, value: Any, where: str) -> Scalar:
    """``value`` as a literal of the parameter ``name``'s type and range."""
    if name == "position":
        return validate_id("position", value) if isinstance(value, str) else _bad(name, where)
    if name == "expiry_cycle":
        return str(value) if value in EXPIRY_CYCLES else _bad(name, where)
    low, high = BOUNDS[name]
    whole = name in INTEGER_AXES
    ok = type(value) is int if whole else isinstance(value, (int, float)) and value is not True
    return cast(Scalar, value) if ok and low <= value <= high else _bad(name, where)


def _bad(name: str, where: str) -> NoReturn:
    raise ConfigurationError(f"{where} {name}: not a value of this parameter's type and range")


def _case_value(name: str, raw: Mapping[str, Any], where: str) -> CaseValue:
    t = Table(raw, f"{where} {name}")
    t.only(("cases", "default"))
    if "default" not in raw or not isinstance(raw.get("cases"), list) or not raw["cases"]:
        raise ConfigurationError(f"{t.where}: needs a non-empty cases list and a default")
    cases = []
    for c in t.tables("cases"):
        c.only(("when", "value"))
        if "when" not in c.names() or "value" not in c.names():
            raise ConfigurationError(f"{c.where}: needs when and value")
        when = when_of(c.raw("when"), f"{c.where} when")
        cases.append(Case(when, _literal(name, c.raw("value"), c.where)))
    return CaseValue(name, tuple(cases), _literal(name, raw["default"], t.where))


def split_cases(o: Table) -> tuple[Table, tuple[CaseValue, ...]]:
    """``o`` with each case table of the case-valued parameters replaced by its ``default``
    literal, and the case values (in a fixed order). A parameter that is not a table is left
    for the outcome's own typing."""
    doc = {k: o.raw(k) for k in o.names()}
    found: list[CaseValue] = []
    for key in CASE_NAMES:
        if isinstance(doc.get(key), Mapping):
            found.append(_case_value(key, doc[key], o.where))
            doc[key] = found[-1].default
    exit_doc = doc.get("exit")
    if isinstance(exit_doc, Mapping):
        exit_doc = dict(exit_doc)
        for key in EXIT_CASE_NAMES:
            if isinstance(exit_doc.get(key), Mapping):
                found.append(_case_value(key, exit_doc[key], f"{o.where} exit"))
                exit_doc[key] = found[-1].default
        doc["exit"] = exit_doc
    return Table(doc, o.where), tuple(found)
