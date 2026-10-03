"""Lexing and parsing: precedence, literals, positions in errors, and that nothing a hostile
formula can say reaches Python: the grammar has no attribute access, indexing, assignment,
statements or names outside lower-case identifiers."""

import pytest

from algotrade.features.expressions.lexer import MAX_LENGTH, tokens
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
from algotrade.features.expressions.parser import MAX_DEPTH, parse_formula

WHERE = "features/x.toml [f] expr"


def show(node: Node) -> str:
    """The tree in prefix form, to check structure (precedence and associativity)."""
    if isinstance(node, Literal):
        return repr(node.value)
    if isinstance(node, Ref):
        return node.name
    if isinstance(node, Unary):
        return f"({node.op} {show(node.operand)})"
    if isinstance(node, Binary):
        return f"({node.op} {show(node.left)} {show(node.right)})"
    return f"{node.func}({', '.join(show(a) for a in node.args)})"


@pytest.mark.parametrize(
    ("text", "tree"),
    [
        ("1 + 2 * 3", "(+ 1.0 (* 2.0 3.0))"),
        ("(1 + 2) * 3", "(* (+ 1.0 2.0) 3.0)"),
        ("a.x - b.y - 1", "(- (- a.x b.y) 1.0)"),
        ("8 / 4 / 2", "(/ (/ 8.0 4.0) 2.0)"),
        ("-a.x * 2", "(* (- a.x) 2.0)"),
        ("- - 1", "(- (- 1.0))"),
        ("a.x > 1 and b.y < 2 or c", "(or (and (> a.x 1.0) (< b.y 2.0)) c)"),
        ("not a.x > 1 and c", "(and (not (> a.x 1.0)) c)"),
        ("a or b and c", "(or a (and b c))"),
        ("a.x + 1 >= b.y * 2", "(>= (+ a.x 1.0) (* b.y 2.0))"),
        ("if(c, 'A', \"B\")", "if(c, 'A', 'B')"),
        ("coalesce(a.x, 0)", "coalesce(a.x, 0.0)"),
        ("is_null(null) == true", "(== is_null(None) True)"),
        ("1e6 + 100_000 + 0.25", "(+ (+ 1000000.0 100000.0) 0.25)"),
        ("'it\\'s'", '"it\'s"'),
        ("a.x # a comment\n + 1", "(+ a.x 1.0)"),
        ("max(a.x, b.y, 3)", "max(a.x, b.y, 3.0)"),
    ],
)
def test_precedence_and_literals(text: str, tree: str) -> None:
    assert show(parse_formula(text, WHERE)) == tree


def test_positions_and_walk() -> None:
    node = parse_formula("a.x +\n  bad.y", WHERE)
    assert isinstance(node, Binary) and node.pos == Pos(1, 5)
    assert node.right.pos == Pos(2, 3)
    assert [type(n).__name__ for n in walk(parse_formula("f(-x, not y)", WHERE))] == [
        "Call", "Unary", "Ref", "Unary", "Ref",
    ]  # fmt: skip
    kinds = [t.kind for t in tokens("a and 'b' 1 <=", WHERE)]
    assert kinds == ["name", "kw", "str", "num", "op", "end"]


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("", "line 1 col 1: empty formula"),
        ("a.x +", "col 6: expected a value"),
        ("(a.x", "expected ')', found 'the end'"),
        ("a.x a.y", "col 5: unexpected 'a.y' after a complete expression"),
        ("a < b < c", "compare once per term"),
        ("'open", "unterminated string"),
        ("a.b.c", "invalid name starting 'a.b'"),
        ("Close", "unexpected character 'C' (names are lower case)"),
        ("1.2.3", "malformed number"),
        (".5", "a number starts with a digit"),
        ("a.x(1)", "'a.x' is not a function"),
        ("f(1,)", "expected a value"),
    ],
)
def test_errors_name_where_and_position(text: str, message: str) -> None:
    with pytest.raises(ExpressionError, match=r"features/x.toml \[f\] expr") as info:
        parse_formula(text, WHERE)
    assert message in str(info.value)


@pytest.mark.parametrize(
    "attack",
    [
        "__import__('os').system('rm -rf /')",
        "open('/etc/passwd').read()",
        "a.x.__class__",
        "eval('1')",  # parses as a call; the checker refuses unknown functions
        "[1, 2]",
        "a.x; import os",
        "lambda: 1",
        "a.x if True else b",
        "x = 1",
        "`id`",
        "a.x[0]",
        "{'a': 1}",
        "exec\n('1')",
        "a.x @ b",
        "1 ** 2",
    ],
)
def test_no_python_reaches_the_language(attack: str) -> None:
    try:
        node = parse_formula(attack, WHERE)
    except ExpressionError:
        return
    # Whatever parses is only literals, references and calls by name: no attribute access.
    calls = [n.func for n in walk(node) if isinstance(n, Call)]
    assert calls in (["eval"], ["exec"], ["lambda"]) or not calls
    assert all("__" not in n.name for n in walk(node) if isinstance(n, Ref))


def test_limits() -> None:
    with pytest.raises(ExpressionError, match="longer than"):
        tokens("1+" * MAX_LENGTH, WHERE)
    with pytest.raises(ExpressionError, match="nested deeper"):
        parse_formula("(" * (MAX_DEPTH + 1) + "1" + ")" * (MAX_DEPTH + 1), WHERE)
    with pytest.raises(ExpressionError, match="nested deeper"):
        parse_formula("-" * (MAX_DEPTH + 1) + "1", WHERE)
    assert isinstance(parse_formula("not " * 10 + "a", WHERE), Unary)
    assert isinstance(parse_formula("f(" * 10 + "1" + ")" * 10, WHERE), Call)
