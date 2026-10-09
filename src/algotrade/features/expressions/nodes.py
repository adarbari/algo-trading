"""The syntax tree of a feature expression, and the error every stage raises.

Every node records where it starts (``Pos``: 1-based line and column in the formula), so an
error names the file, the feature and the position: ``config/site/features/technical/price.toml
[near_52w] expr, line 1 col 14: unknown feature 'price_stats.clsoe'``.
"""

from dataclasses import dataclass

from algotrade.core.model.errors import ConfigurationError

type Scalar = float | str | bool | None


@dataclass(frozen=True)
class Pos:
    line: int
    col: int


class ExpressionError(ConfigurationError):
    """A formula that does not lex, parse or type check (or a bad definition around it)."""

    def __init__(self, where: str, pos: Pos | None, message: str) -> None:
        self.where, self.pos, self.message = where, pos, message
        at = f", line {pos.line} col {pos.col}" if pos is not None else ""
        super().__init__(f"{where}{at}: {message}")


@dataclass(frozen=True)
class Literal:
    """A number, string, ``true`` / ``false`` or ``null``."""

    value: Scalar
    pos: Pos


@dataclass(frozen=True)
class Ref:
    """A name: ``group.column`` (a stored feature), an expression feature, or a parameter."""

    name: str
    pos: Pos


@dataclass(frozen=True)
class Unary:
    op: str  # "-" or "not"
    operand: "Node"
    pos: Pos


@dataclass(frozen=True)
class Binary:
    op: str  # + - * / < <= > >= == != and or
    left: "Node"
    right: "Node"
    pos: Pos


@dataclass(frozen=True)
class Call:
    func: str
    args: tuple["Node", ...]
    pos: Pos


type Node = Literal | Ref | Unary | Binary | Call


def children(node: Node) -> list[Node]:
    """The direct operands of ``node``."""
    if isinstance(node, Unary):
        return [node.operand]
    if isinstance(node, Binary):
        return [node.left, node.right]
    if isinstance(node, Call):
        return list(node.args)
    return []


def walk(node: Node) -> list[Node]:
    """``node`` and every node below it, depth first."""
    out: list[Node] = [node]
    if isinstance(node, Unary):
        out += walk(node.operand)
    elif isinstance(node, Binary):
        out += walk(node.left) + walk(node.right)
    elif isinstance(node, Call):
        for arg in node.args:
            out += walk(arg)
    return out
