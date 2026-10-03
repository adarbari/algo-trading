"""Expression features from their site definitions: parsed, parameters bound, names resolved,
the dependency graph checked and every formula type checked against the catalogue.

``build_expressions(definitions, groups)`` returns each ``Expression`` by name in dependency
order (an expression after the expressions it reads). A formula names stored features as
``group.column`` (the registered version of that group: ``price_stats.hv30`` is
``price_stats.hv30@v2`` today), other expression features by name, and its own ``params`` by
name (bound as literals, so a threshold is data, not code). Any problem fails the whole load
with the file, the feature and the position: an unknown or ambiguous name, an unused
parameter, a cycle (named as a path), a type error, a result that does not fit the declared
``dtype``, or a label value outside the declared ``categories``.
"""

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from algotrade.config.site.settings import FeatureDefinition
from algotrade.features.expressions.checker import check_formula
from algotrade.features.expressions.evaluator import KIND_OF
from algotrade.features.expressions.functions import OPEN_STR, Type
from algotrade.features.expressions.nodes import (
    Binary,
    Call,
    ExpressionError,
    Literal,
    Node,
    Pos,
    Ref,
    Unary,
    walk,
)
from algotrade.features.expressions.parser import parse_formula
from algotrade.features.framework.declaration import FeatureGroup
from algotrade.features.framework.feature import Feature, feature_problems

_NAME = re.compile(r"^[a-z][a-z0-9_]*$")


@dataclass(frozen=True)
class Expression:
    """One expression feature: its ``Feature`` (no group; key ``<name>@v<N>``), the checked
    formula with parameters bound, and what it reads: stored features (``refs``,
    ``group.column``), other expression features (``uses``) and groups in ``exists``."""

    feature: Feature
    definition: FeatureDefinition
    node: Node
    type: Type
    refs: tuple[str, ...]
    uses: tuple[str, ...]
    exists: tuple[str, ...]

    @property
    def name(self) -> str:
        return self.feature.name

    @property
    def materialise(self) -> bool:
        return self.definition.materialise


def feature_type(dtype: str, categories: Sequence[str] = ()) -> Type:
    kind = KIND_OF[dtype]
    if kind == "str":
        return Type("str", frozenset(categories)) if categories else OPEN_STR
    return Type(kind)


def _bind(node: Node, params: Mapping[str, object]) -> Node:
    """``node`` with each parameter reference replaced by its value."""
    if isinstance(node, Ref) and node.name in params:
        return Literal(params[node.name], node.pos)  # type: ignore[arg-type]
    if isinstance(node, Unary):
        return Unary(node.op, _bind(node.operand, params), node.pos)
    if isinstance(node, Binary):
        return Binary(node.op, _bind(node.left, params), _bind(node.right, params), node.pos)
    if isinstance(node, Call):
        if node.func == "exists":
            return node
        return Call(node.func, tuple(_bind(a, params) for a in node.args), node.pos)
    return node


def _names(node: Node) -> tuple[list[Ref], list[str]]:
    """References (outside ``exists``) and the groups named in ``exists(...)``."""
    refs: list[Ref] = []
    exists: list[str] = []
    for n in walk(node):
        if isinstance(n, Call) and n.func == "exists":
            exists += [a.name for a in n.args if isinstance(a, Ref)]
        elif isinstance(n, Ref):
            refs.append(n)
    return [r for r in refs if r.name not in exists or "." in r.name], exists


class _Scope:
    def __init__(
        self, where: str, groups: Mapping[str, FeatureGroup], declared: Mapping[str, Type]
    ) -> None:
        self.where, self.groups, self.declared = where, groups, declared

    def is_group(self, name: str) -> bool:
        return name in self.groups

    def ref_type(self, name: str, pos: Pos) -> Type:
        if "." not in name:
            if name not in self.declared:
                raise ExpressionError(self.where, pos, f"unknown name {name!r}")
            return self.declared[name]
        group, _, column = name.partition(".")
        if group not in self.groups:
            known = ", ".join(sorted(self.groups))
            raise ExpressionError(self.where, pos, f"unknown feature group {group!r} ({known})")
        g = self.groups[group]
        if column not in g.columns:
            known = ", ".join(g.columns)
            raise ExpressionError(self.where, pos, f"{g.key} has no feature {column!r} ({known})")
        f = g.feature(column)
        return feature_type(f.dtype, f.categories)


def _parse(d: FeatureDefinition, taken: Mapping[str, str]) -> tuple[Node, list[Ref], list[str]]:
    """The formula with params bound -> (node, references, exists groups)."""
    where = f"{d.where} expr"
    node = parse_formula(d.expr, where)
    clash = sorted(p for p in d.params if p in taken or not _NAME.match(p))
    if clash:
        raise ExpressionError(d.where, None, f"params {clash}: not a name, or taken by a feature")
    used = {n.name for n in walk(node) if isinstance(n, Ref)}
    unused = sorted(set(d.params) - used)
    if unused:
        raise ExpressionError(d.where, None, f"params {unused} are not used in expr")
    node = _bind(node, d.params)
    refs, exists = _names(node)
    return node, refs, exists


def _order(uses: Mapping[str, tuple[str, ...]], where: Mapping[str, str]) -> list[str]:
    """Names with every dependency first; a cycle fails naming it."""
    done: list[str] = []
    state: dict[str, str] = {}

    def visit(name: str, path: list[str]) -> None:
        if state.get(name) == "done":
            return
        if state.get(name) == "active":
            cycle = [*path[path.index(name) :], name]
            raise ExpressionError(where[name], None, f"dependency cycle: {' -> '.join(cycle)}")
        state[name] = "active"
        for dep in uses[name]:
            if dep in uses:  # an unknown name fails in the type check, with its position
                visit(dep, [*path, name])
        state[name] = "done"
        done.append(name)

    for name in uses:
        visit(name, [])
    return done


def _feature(d: FeatureDefinition, inputs: tuple[str, ...]) -> Feature:
    f = Feature(
        d.name, d.dtype, d.unit, d.description, d.null_meaning, d.kind,  # type: ignore[arg-type]
        valid_range=d.valid_range, categories=d.categories, inputs=inputs, version=d.version,
    )  # fmt: skip
    problems = feature_problems(f)
    if d.kind == "label" and not d.categories:
        problems.append(f"{d.name}: a label declares its categories")
    if problems:
        raise ExpressionError(d.where, None, "; ".join(problems))
    return f


def build_expressions(
    definitions: Sequence[FeatureDefinition], groups: Mapping[str, FeatureGroup]
) -> dict[str, Expression]:
    """Every definition as a checked ``Expression``, by name, in dependency order.
    ``groups``: the registered feature groups by key (one version per group name)."""
    by_name = {g.name: g for g in groups.values()}
    defs: dict[str, FeatureDefinition] = {}
    for d in definitions:
        if d.name in defs or d.name in by_name:
            raise ExpressionError(d.where, None, f"{d.name!r} is already a feature or group name")
        defs[d.name] = d
    for d in defs.values():
        _feature(d, ())  # dtype, unit, kind, range and categories, before any formula
    taken = {**dict.fromkeys(by_name, "group"), **dict.fromkeys(defs, "feature")}
    parsed = {name: _parse(d, taken) for name, d in defs.items()}
    uses = {
        n: tuple(sorted({r.name for r in p[1] if "." not in r.name})) for n, p in parsed.items()
    }
    declared = {n: feature_type(d.dtype, d.categories) for n, d in defs.items()}
    out: dict[str, Expression] = {}
    for name in _order(uses, {n: d.where for n, d in defs.items()}):
        d, (node, refs, exists) = defs[name], parsed[name]
        where = f"{d.where} expr"
        result = check_formula(node, _Scope(where, by_name, declared), where)
        _fits(d, result)
        stored = tuple(sorted({r.name for r in refs if "." in r.name}))
        inputs = tuple(
            [f"{s}@v{by_name[s.partition('.')[0]].version}" for s in stored]
            + [out[u].feature.key for u in uses[name]]
        )
        feature = _feature(d, inputs)
        out[name] = Expression(feature, d, node, result, stored, uses[name], tuple(exists))
    return out


def _fits(d: FeatureDefinition, result: Type) -> None:
    want = KIND_OF[d.dtype]
    if result.kind != want:
        raise ExpressionError(d.where, None, f"expr gives {result}, but dtype is {d.dtype}")
    if want == "str" and d.categories and result.categories is not None:
        extra = sorted(result.categories - set(d.categories))
        if extra:
            raise ExpressionError(d.where, None, f"expr can give {extra}, not in categories")
