"""A stable fingerprint of a formula, so the same formula written differently is found
(Describe-it plan, "Features and duplicates"): a feature the trader's sentence would define
again is dropped and the existing field used.

The formula is parsed by the expression parser, its ``params`` are bound as literals, and the
tree is normalised, then printed as a prefix text (the canonical form) and hashed:

- whitespace and parentheses are irrelevant (the tree has neither);
- constants are folded (``2 * 3`` is ``6``; ``-(1)`` is ``-1``);
- ``a - c`` with a constant ``c`` is ``a + (-c)``, and ``a > b`` is ``b < a`` (likewise
  ``>=``), so a threshold written either way matches;
- the operands of ``+ * min max and or == !=`` are flattened and sorted; ``a - b`` and
  ``a / b`` keep their order.

Names are kept as written: ``group.column`` for a stored feature, a bare name for another
expression feature (a ``group.column`` is one registered version today, so no version is
added). The limit: this is syntactic, not algebra. ``(x-y)/y`` and ``x/y-1`` are different
fingerprints (merged by an admin by hand), and a sum is reordered as if exact, ignoring
floating-point rounding.
"""

import hashlib
from collections.abc import Callable, Iterable
from dataclasses import dataclass

from algotrade.config.site.features.definitions import FeatureDefinition
from algotrade.core.model.errors import ConfigurationError
from algotrade.features.expressions.definitions import bind_params
from algotrade.features.expressions.nodes import Binary, Call, Literal, Node, Ref, Unary
from algotrade.features.expressions.parser import parse_formula

HASH_LENGTH = 12
_FLAT = frozenset({"+", "*", "and", "or"})  # associative and commutative: chains are flattened
_SORTED = _FLAT | {"==", "!="}
_SORTED_CALLS = frozenset({"min", "max"})
_MIRROR = {">": "<", ">=": "<="}
_ARITH: dict[str, Callable[[float, float], float]] = {
    "+": lambda a, b: a + b,
    "-": lambda a, b: a - b,
    "*": lambda a, b: a * b,
}


@dataclass(frozen=True)
class Fingerprint:
    hash: str  # a short stable hex digest of ``text``
    text: str  # the canonical form


def fingerprint(definition: FeatureDefinition) -> Fingerprint:
    """The fingerprint of ``definition.expr`` with its ``params`` bound. An invalid formula
    raises ``ExpressionError``."""
    where = f"{definition.name} expr"
    node = bind_params(parse_formula(definition.expr, where), definition.params)
    text = _canon(_normal(node))
    return Fingerprint(hashlib.sha256(text.encode()).hexdigest()[:HASH_LENGTH], text)


def find_duplicate(
    wanted: Fingerprint,
    site_features: Iterable[FeatureDefinition],
    user_features: Iterable[FeatureDefinition],
) -> str | None:
    """The name of the first feature whose fingerprint equals ``wanted``: the site's, then the
    trader's own; ``None`` when there is none. A definition that does not parse is skipped."""
    for definition in (*site_features, *user_features):
        try:
            if fingerprint(definition).hash == wanted.hash:
                return definition.name
        except ConfigurationError:
            continue
    return None


def _const(node: Node) -> float | None:
    if isinstance(node, Literal) and isinstance(node.value, int | float):
        return None if isinstance(node.value, bool) else float(node.value)
    return None


def _lit(value: float | bool, like: Node) -> Literal:
    return Literal(value, like.pos)


def _normal(node: Node) -> Node:
    if isinstance(node, Unary):
        return _unary(node)
    if isinstance(node, Binary):
        return _binary(node)
    if isinstance(node, Call):
        args = tuple(_normal(a) for a in node.args)
        if node.func in _SORTED_CALLS:
            args = tuple(sorted(args, key=_canon))
        return Call(node.func, args, node.pos)
    return node


def _unary(node: Unary) -> Node:
    operand = _normal(node.operand)
    value = _const(operand)
    if node.op == "-" and value is not None:
        return _lit(-value, node)
    if node.op == "not" and isinstance(operand, Literal) and isinstance(operand.value, bool):
        return _lit(not operand.value, node)
    return Unary(node.op, operand, node.pos)


def _binary(node: Binary) -> Node:
    op, left, right = node.op, _normal(node.left), _normal(node.right)
    shift = _const(right)
    if op == "-" and shift is not None:  # a - c  ->  a + (-c)
        op, right = "+", _lit(-shift, right)
    if op in _MIRROR:
        op, left, right = _MIRROR[op], right, left
    a, b = _const(left), _const(right)
    if a is not None and b is not None:
        if op in _ARITH:
            return _lit(_ARITH[op](a, b), node)
        if op == "/" and b != 0.0:
            return _lit(a / b, node)
    if op in _FLAT:
        return _flat(op, [left, right], node)
    if op in _SORTED:
        left, right = sorted((left, right), key=_canon)
    return Binary(op, left, right, node.pos)


def _flat(op: str, parts: list[Node], like: Node) -> Node:
    """``a op b op c ...`` as one chain, constants folded, operands sorted."""
    flat = [leaf for part in parts for leaf in _chain(part, op)]
    if op in _ARITH:  # fold every numeric constant of a sum or product into one
        constants = [v for v in (_const(p) for p in flat) if v is not None]
        rest = [p for p in flat if _const(p) is None]
        if constants:
            folded = constants[0]
            for c in constants[1:]:
                folded = _ARITH[op](folded, c)
            identity = 0.0 if op == "+" else 1.0
            if folded != identity or not rest:
                rest.append(_lit(folded, like))
        flat = rest
    flat.sort(key=_canon)
    out = flat[0]
    for nxt in flat[1:]:
        out = Binary(op, out, nxt, like.pos)
    return out


def _chain(node: Node, op: str) -> list[Node]:
    if isinstance(node, Binary) and node.op == op:
        return _chain(node.left, op) + _chain(node.right, op)
    return [node]


def _scalar(value: float | str | bool | None) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return f"{float(value):.12g}"


def _canon(node: Node) -> str:
    if isinstance(node, Literal):
        return _scalar(node.value)
    if isinstance(node, Ref):
        return node.name
    if isinstance(node, Unary):
        return f"({node.op} {_canon(node.operand)})"
    if isinstance(node, Binary):
        parts = _chain(node, node.op) if node.op in _FLAT else [node.left, node.right]
        return f"({node.op} {' '.join(_canon(p) for p in parts)})"
    return f"({node.func} {' '.join(_canon(a) for a in node.args)})".replace(" )", ")")
