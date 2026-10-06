"""Type check a formula before it ever runs: every name resolves, every operator and function
gets the types it takes, and a string compared with a label is one of the label's categories.

``check_formula(node, scope, where)`` returns the formula's ``Type`` or raises
``ExpressionError`` at the offending position. ``scope`` resolves names
(``Scope.ref_type``: a stored feature ``group.column``, an expression feature, or a parameter
bound as a literal) and says which names are feature groups (for ``exists(group)``).

Rules: ``+ - * /`` and unary ``-`` take numbers; ``< <= > >=`` numbers, strings or dates of
the same type; ``== !=`` any two values of the same type (never ``null``: use ``is_null``);
``and or not`` take bools; ``if`` takes a bool and two branches of one type (``null`` fits
any); ``min`` / ``max`` numbers or strings; ``coalesce`` values of one type; ``abs log sqrt
ncdf clip`` numbers; ``one_of(x, literals...)`` literals of x's type; ``exists`` a group name.
"""

from collections.abc import Sequence
from typing import Protocol

from algotrade.features.expressions.functions import (
    BOOL,
    FUNCTIONS,
    NULL,
    NUM,
    OPEN_STR,
    Type,
    unify,
)
from algotrade.features.expressions.nodes import (
    Binary,
    Call,
    ExpressionError,
    Literal,
    Node,
    Pos,
    Ref,
    Unary,
)

ORDERED = frozenset({"num", "str", "date"})


class Scope(Protocol):
    def ref_type(self, name: str, pos: Pos) -> Type:
        """The type of a name; raises ``ExpressionError`` for an unknown one."""
        ...

    def is_group(self, name: str) -> bool: ...


def literal_type(value: object) -> Type:
    if value is None:
        return NULL
    if isinstance(value, bool):
        return BOOL
    if isinstance(value, str):
        return Type("str", frozenset({value}))
    return NUM


class _Checker:
    def __init__(self, scope: Scope, where: str) -> None:
        self.scope, self.where = scope, where

    def fail(self, pos: Pos, message: str) -> ExpressionError:
        return ExpressionError(self.where, pos, message)

    def want(self, node: Node, kinds: frozenset[str] | str, what: str) -> Type:
        t = self.check(node)
        allowed = {kinds} if isinstance(kinds, str) else set(kinds)
        if t.kind not in allowed and t.kind != "null":
            raise self.fail(node.pos, f"{what} takes {' or '.join(sorted(allowed))}, not {t}")
        return t

    def check(self, node: Node) -> Type:
        if isinstance(node, Literal):
            return literal_type(node.value)
        if isinstance(node, Ref):
            return self.scope.ref_type(node.name, node.pos)
        if isinstance(node, Unary):
            if node.op == "-":
                self.want(node.operand, "num", "unary -")
                return NUM
            self.want(node.operand, "bool", "not")
            return BOOL
        if isinstance(node, Binary):
            return self.binary(node)
        return self.call(node)

    def binary(self, node: Binary) -> Type:
        if node.op in ("+", "-", "*", "/"):
            self.want(node.left, "num", node.op)
            self.want(node.right, "num", node.op)
            return NUM
        if node.op in ("and", "or"):
            self.want(node.left, "bool", node.op)
            self.want(node.right, "bool", node.op)
            return BOOL
        left, right = self.check(node.left), self.check(node.right)
        if "null" in (left.kind, right.kind):
            raise self.fail(node.pos, f"{node.op} with null is always null: use is_null(x)")
        if left.kind != right.kind:
            raise self.fail(node.pos, f"cannot compare {left} with {right}")
        if node.op not in ("==", "!=") and left.kind not in ORDERED:
            raise self.fail(node.pos, f"{node.op} orders numbers, strings or dates, not {left}")
        self.categories(node.left, left, node.right, right)
        return BOOL

    def categories(self, a: Node, ta: Type, b: Node, tb: Type) -> None:
        """A string literal compared with a label must be one of its categories."""
        for lit, other in ((a, tb), (b, ta)):
            if isinstance(lit, Literal) and isinstance(lit.value, str) and other.kind == "str":
                cats = other.categories
                if cats is not None and lit.value not in cats:
                    raise self.fail(
                        lit.pos, f"{lit.value!r} is never a value here: one of {sorted(cats)}"
                    )

    def call(self, node: Call) -> Type:
        fn = FUNCTIONS.get(node.func)
        if fn is None:
            raise self.fail(node.pos, f"unknown function {node.func!r}; known: {sorted(FUNCTIONS)}")
        n = len(node.args)
        if (fn.variadic and n < fn.arity) or (not fn.variadic and n != fn.arity):
            count = f"at least {fn.arity}" if fn.variadic else str(fn.arity)
            raise self.fail(node.pos, f"{node.func} takes {count} arguments, got {n}")
        rule = {
            "exists": self.exists,
            "if": self.if_,
            "min": self.extreme,
            "max": self.extreme,
            "coalesce": lambda c: self.same(c.args, c, "coalesce"),
            "is_null": self.is_null,
            "one_of": self.one_of,
        }.get(node.func, self.numeric)
        return rule(node)

    def exists(self, node: Call) -> Type:
        arg = node.args[0]
        if not (isinstance(arg, Ref) and self.scope.is_group(arg.name)):
            raise self.fail(arg.pos, "exists takes a feature group name, e.g. exists(price_stats)")
        return BOOL

    def if_(self, node: Call) -> Type:
        self.want(node.args[0], "bool", "if (condition)")
        return self.same(node.args[1:], node, "if branches")

    def extreme(self, node: Call) -> Type:
        for arg in node.args:
            self.want(arg, frozenset({"num", "str"}), node.func)
        return self.same(node.args, node, node.func)

    def is_null(self, node: Call) -> Type:
        self.check(node.args[0])
        return BOOL

    def numeric(self, node: Call) -> Type:  # abs, sqrt, log, ncdf, clip
        for arg in node.args:
            self.want(arg, "num", node.func)
        return NUM

    def same(self, args: Sequence[Node], node: Call, what: str) -> Type:
        types = [self.check(a) for a in args]
        common = unify(types)
        if common is None:
            raise self.fail(
                node.pos, f"{what} must have one type, got {', '.join(map(str, types))}"
            )
        if common.kind == "null":
            raise self.fail(node.pos, f"{what} are all null")
        return common

    def one_of(self, node: Call) -> Type:
        x = self.want(node.args[0], frozenset({"num", "str"}), "one_of")
        for arg in node.args[1:]:
            if not isinstance(arg, Literal) or arg.value is None:
                raise self.fail(arg.pos, "one_of takes literal values after the first argument")
            t = literal_type(arg.value)
            if t.kind != x.kind:
                raise self.fail(arg.pos, f"one_of: {arg.value!r} is not a {x.kind}")
            self.categories(arg, t, node.args[0], x)
        return BOOL


def check_formula(node: Node, scope: Scope, where: str) -> Type:
    """The type of ``node``. Raises ``ExpressionError`` at the first problem."""
    return _Checker(scope, where).check(node)


__all__ = ["OPEN_STR", "Scope", "Type", "check_formula", "literal_type"]
