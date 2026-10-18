"""``group_parts``: the boolean groups of a draft, from the ``join`` of its parts (ADR 0071,
"Describe it"). A part's join says how it relates to the one before it (``parts/connectors``): a
run of parts joined by ``or`` becomes an ``any`` group, a part joined by ``and_not`` (with the
parts an "or" or "and" adds to the exclusion) a ``none`` group, and ``(A and B) or C`` an ``all``
inside an ``any``, so none of them needs a formula. Each criterion keeps the mode its words ask
for ("ideally" is ``score``), also inside a group; the groups name criteria by id and are the
spec's ``groups`` table.

Precedence is decided per phrasing (the golden cases under ``tests/fixtures/drafting/golden`` pin
each one, the owner verifies them), and these are the readings the code gives:

- ``and`` binds tighter than ``or``: "A or B and C" is ``A or (B and C)``, "A and B, or C" is
  ``(A and B) or C``;
- no connector at all, a comma or "ideally" before a part ("A, ideally B or C") starts a new
  sentence-level condition: the sentence is the AND of its segments, and an "or" never reaches
  across the break, so that one is ``A and (B or C)``;
- an exclusion is its own gate and covers the parts an "or" or a plain "and" adds to it: "except
  A or B" and "except A and B" are both "none of A, B"; "A or B except C" is ``(A or B)`` and
  ``not C``. Any other connector ("but", "also") ends the exclusion;
- the part that only names the kind of instrument ("stocks", "ETFs": the scope fields below) is
  no operand: its criteria stay top-level, so "stocks with A or B" is ``stocks and (A or B)``.

Grouping applies only when every part of a segment that has an "or" or an exclusion is a plain
one (applied, or a term with a default, with criteria in the draft): a pending formula, a missing
request, a dropped criterion or a part nothing maps cannot sit in a group, so the draft stays flat
as it was and ``blocked`` names the formula parts, which the verifier doubts (``parts/verify``:
the whole "or" is then one boolean formula). Pure: reads parts and criteria, calls nothing."""

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from algotrade.services.drafting.parts.connectors import AND, AND_NOT, OR
from algotrade.services.drafting.parts.model import Part

SCOPE_FIELDS = frozenset(
    {"instrument.status", "instrument.security_type", "instrument.is_etf"}
)  # what names the kind of instrument: never an operand of an "or"
PLAIN_KINDS = ("applied", "needs_choice")
_AND_WORD = re.compile(r"^\W*and\W*$", re.IGNORECASE)  # the plain "and" that extends an exclusion


@dataclass(frozen=True)
class Grouping:
    """``groups``: the spec's ``groups`` table (id -> ``{"any" | "all" | "none": [member ids]}``),
    empty when nothing is grouped; ``blocked``: ids of the parts with a pending formula that sit
    in an "or" or an exclusion, which kept the draft flat."""

    groups: dict[str, dict[str, list[str]]] = field(default_factory=dict)
    blocked: tuple[str, ...] = ()


@dataclass(frozen=True)
class _Row:
    part: Part
    logic: str  # how it relates to the previous row of its segment (``AND`` for the first)
    ids: tuple[str, ...]  # the criteria it is an operand with
    extends: bool  # the connector is a plain "and" (not "but", "also"): may extend an exclusion


class _Names:
    """Group ids that collide with no criterion and no other group."""

    def __init__(self, taken: set[str]) -> None:
        self.taken = taken

    def next(self, kind: str) -> str:
        n = 1
        while f"{kind}_{n}" in self.taken:
            n += 1
        self.taken.add(f"{kind}_{n}")
        return f"{kind}_{n}"


def group_parts(
    parts: Sequence[Part] | None, criteria: Mapping[str, Any] | None = None
) -> Grouping:
    """The groups of ``parts``' joins over the draft's ``criteria`` (id -> criterion; ``None``:
    every criterion id a part names, no scope filtering)."""
    busy = [
        seg
        for seg in _segments(parts or (), criteria)
        if any(r.logic in (OR, AND_NOT) for r in seg)
    ]
    dirty = [r for seg in busy for r in seg if not _plain(r)]
    if dirty:  # a formula, a request, a dropped criterion: the draft stays flat
        return Grouping({}, tuple(r.part.id for r in dirty if r.part.formulas))
    names = _Names(set(criteria or ()))
    groups: dict[str, dict[str, list[str]]] = {}
    for seg in busy:
        _build(seg, names, groups)
    return Grouping(groups)


def _plain(row: _Row) -> bool:
    part = row.part
    return part.kind in PLAIN_KINDS and bool(row.ids) and not part.formulas


def _segments(parts: Sequence[Part], criteria: Mapping[str, Any] | None) -> list[list[_Row]]:
    """The operands in sentence order, cut into segments where no connector lies between two
    parts (catch-alls, and parts that only name the kind of instrument, are no operands)."""
    segments: list[list[_Row]] = []
    for part in parts:
        if part.origin not in ("words", "gap"):
            continue
        if _scope_only(part, criteria) and part.join in (None, AND):
            continue
        if part.join is None or not segments:
            segments.append([])
        seg = segments[-1]
        logic = part.join or AND
        if not seg and logic != AND_NOT:  # an "or" or "and" with nothing before it
            logic = AND
        seg.append(
            _Row(part, logic, _ids(part, criteria, logic), bool(_AND_WORD.match(part.join_words)))
        )
    return segments


def _scope_only(part: Part, criteria: Mapping[str, Any] | None) -> bool:
    """Whether ``part`` holds criteria and every one names the kind of instrument."""
    if criteria is None or not part.criteria or part.formulas or part.missing or part.dropped:
        return False
    return all(c in criteria and criteria[c].get("field") in SCOPE_FIELDS for c in part.criteria)


def _ids(part: Part, criteria: Mapping[str, Any] | None, logic: str) -> tuple[str, ...]:
    """The criteria of ``part`` that are its operands: its scope criteria stay top-level (all
    but the status scaffolding in an exclusion, where "except ETFs" must name the ETFs)."""
    if criteria is None:
        return part.criteria
    skip = SCOPE_FIELDS if logic != AND_NOT else {"instrument.status"}
    return tuple(c for c in part.criteria if c in criteria and criteria[c].get("field") not in skip)


def _build(seg: list[_Row], names: _Names, groups: dict[str, dict[str, list[str]]]) -> None:
    """Add the groups of one segment: its exclusions as one ``none``, its alternatives (cut at
    each "or", an and-run inside each) as an ``any`` when there are two or more."""
    alternatives: list[list[str]] = []
    excluded: list[str] = []
    excluding = False
    for row in seg:
        if row.logic == AND_NOT or (
            excluding and (row.logic == OR or (row.extends and row.logic == AND))
        ):
            excluding = True
            excluded.append(_operand(row.ids, names, groups))
            continue
        excluding = False
        if row.logic == OR and alternatives:
            alternatives.append(list(row.ids))
        else:
            if not alternatives:
                alternatives.append([])
            alternatives[-1].extend(row.ids)
    if excluded:
        groups[names.next("none")] = {"none": excluded}
    if len(alternatives) >= 2:
        members = [_operand(tuple(alt), names, groups) for alt in alternatives]
        groups[names.next("any")] = {"any": members}


def _operand(ids: tuple[str, ...], names: _Names, groups: dict[str, dict[str, list[str]]]) -> str:
    """One member for several criteria that go together: themselves, or an ``all`` of them."""
    if len(ids) == 1:
        return ids[0]
    gid = names.next("all")
    groups[gid] = {"all": list(ids)}
    return gid


def prune_groups(
    groups: Mapping[str, Any] | None, criteria: Mapping[str, Any]
) -> dict[str, dict[str, list[str]]]:
    """``groups`` (a spec's table) without the members that are not in ``criteria`` or in the
    table, and without the groups that fall under their size (``all`` / ``any`` 2, ``none`` 1),
    until it is stable: what a draft keeps of a document's groups when criteria changed."""
    table = {
        gid: {kind: [m for m in members if isinstance(m, str)]}
        for gid, body in (groups or {}).items()
        if isinstance(body, Mapping)
        for kind, members in body.items()
        if kind in ("all", "any", "none") and isinstance(members, list)
    }
    while True:
        known = set(criteria) | set(table)
        small = [
            gid
            for gid, body in table.items()
            for kind, members in body.items()
            if len([m for m in members if m in known]) < (1 if kind == "none" else 2)
        ]
        if not small:
            return {
                gid: {kind: [m for m in members if m in known] for kind, members in body.items()}
                for gid, body in table.items()
            }
        for gid in small:
            del table[gid]
