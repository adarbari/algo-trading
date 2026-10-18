"""Parse and validate the ``[groups.<id>]`` tables of a rule screen (ADR 0071) into
``CriterionGroup`` values. Fails closed with the path of the problem.

A group holds exactly one of ``all`` / ``any`` / ``none`` (a list of criterion or group ids)
and an optional ``enabled``. One key space with the criteria; every criterion and group has at
most one parent; the graph is acyclic and at most ``MAX_DEPTH`` groups deep; a group with no
parent is a gate, and a top-level ``all`` is refused (it is the screen itself). Layers drop what
they disable before the size rules apply: a disabled criterion leaves its group, a disabled
group leaves its parent and takes its own members (criteria and groups) out of the screen.
"""

from collections.abc import Iterable, Mapping
from typing import Any

from algotrade.core.model.errors import ConfigurationError
from algotrade.core.model.ids import validate_id
from algotrade.core.model.screen_spec import GROUP_KINDS, CriterionGroup

MAX_DEPTH = 4
MAX_MEMBERS = 12
_MIN_MEMBERS = {"all": 2, "any": 2, "none": 1}
_KEYS = frozenset({*GROUP_KINDS, "enabled"})
_SCORE = "score"  # the model screen's gate id (``screen_spec.SCORE_CRITERION``)


def _fail(path: str, message: str) -> ConfigurationError:
    return ConfigurationError(f"{path}: {message}")


def _body(gid: str, raw: Any, path: str) -> tuple[str, tuple[str, ...], bool]:
    if not isinstance(raw, Mapping):
        raise _fail(path, "expected a table")
    unknown = set(raw) - _KEYS
    if unknown:
        raise _fail(path, f"unknown keys {sorted(unknown)}")
    kinds = [k for k in GROUP_KINDS if k in raw]
    if len(kinds) != 1:
        raise _fail(path, "a group has exactly one of 'all', 'any' or 'none'")
    kind = kinds[0]
    members = raw[kind]
    if (
        not isinstance(members, list)
        or not all(isinstance(m, str) and m for m in members)
        or len(set(members)) != len(members)
    ):
        raise _fail(f"{path}.{kind}", "expected a list of distinct criterion or group ids")
    if gid in members:
        raise _fail(f"{path}.{kind}", f"{gid!r} cannot contain itself")
    enabled = raw.get("enabled", True)
    if not isinstance(enabled, bool):
        raise _fail(f"{path}.enabled", "expected true or false")
    return kind, tuple(members), enabled


def _depth(
    gid: str, members: Mapping[str, tuple[str, ...]], path: str, seen: tuple[str, ...]
) -> int:
    """Groups from ``gid`` down (1 for a group of criteria); a cycle is an error."""
    if gid in seen:
        raise _fail(path, f"groups form a cycle: {' -> '.join((*seen, gid))}")
    below = [_depth(m, members, path, (*seen, gid)) for m in members[gid] if m in members]
    return 1 + max(below, default=0)


def _taken_out(disabled: set[str], members: Mapping[str, tuple[str, ...]]) -> set[str]:
    """Every id under a disabled group (its own included)."""
    out: set[str] = set()
    stack = list(disabled)
    while stack:
        gid = stack.pop()
        if gid in out:
            continue
        out.add(gid)
        stack.extend(members.get(gid, ()))
    return out


def _parents(
    bodies: Mapping[str, tuple[str, tuple[str, ...], bool]], known: set[str], path: str
) -> dict[str, str]:
    """Each member's one parent; unknown members and a second parent are errors."""
    parent: dict[str, str] = {}
    for gid, (kind, members, _) in bodies.items():
        for member in members:
            where = f"{path}.{gid}.{kind}"
            if member not in known and member not in bodies:
                raise _fail(where, f"unknown criterion or group {member!r}")
            if member in parent:
                raise _fail(where, f"{member!r} is already a member of {parent[member]!r}")
            parent[member] = gid
    return parent


def _check_shape(
    bodies: Mapping[str, tuple[str, tuple[str, ...], bool]], parent: Mapping[str, str], path: str
) -> None:
    names = {gid: members for gid, (_, members, _) in bodies.items()}
    for gid, (kind, _, enabled) in bodies.items():
        where = f"{path}.{gid}"
        if (depth := _depth(gid, names, where, ())) > MAX_DEPTH:
            raise _fail(where, f"groups nest at most {MAX_DEPTH} deep (this one has {depth})")
        if enabled and kind == "all" and gid not in parent:
            raise _fail(
                where, "a top-level 'all' is the screen itself: list its members as criteria"
            )


def parse_groups(
    raw: Any,
    enabled_criteria: Iterable[str],
    disabled_criteria: Iterable[str],
    path: str,
) -> tuple[tuple[CriterionGroup, ...], frozenset[str]]:
    """``(groups, taken_out)``: the enabled groups in the file's order (members that a layer
    disabled already removed) and the criterion ids a disabled group takes out of the screen."""
    if not isinstance(raw, Mapping):
        raise _fail(path, "expected a table")
    criteria, off = set(enabled_criteria), set(disabled_criteria)
    bodies: dict[str, tuple[str, tuple[str, ...], bool]] = {}
    for gid, body in raw.items():
        where = f"{path}.{gid}"
        validate_id("group", gid)
        if gid == _SCORE or gid in criteria or gid in off:
            raise _fail(where, "a group shares one key space with the criteria: use another id")
        bodies[gid] = _body(gid, body, where)
    _check_shape(bodies, _parents(bodies, criteria | off, path), path)
    names = {gid: members for gid, (_, members, _) in bodies.items()}
    out = _taken_out({g for g, (_, _, enabled) in bodies.items() if not enabled}, names)
    groups = []
    for gid, (kind, members, enabled) in bodies.items():
        if gid in out:
            continue
        kept = tuple(m for m in members if m not in off and m not in out)
        where = f"{path}.{gid}.{kind}"
        if len(kept) < _MIN_MEMBERS[kind]:
            raise _fail(where, f"'{kind}' needs at least {_MIN_MEMBERS[kind]} enabled members")
        if len(kept) > MAX_MEMBERS:
            raise _fail(where, f"at most {MAX_MEMBERS} members")
        groups.append(CriterionGroup(gid, kind, kept, enabled))
    return tuple(groups), frozenset(out & criteria)
