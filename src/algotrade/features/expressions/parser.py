"""Parse a formula into a syntax tree (``nodes``), by recursive descent.

Precedence, lowest first (operators of one level associate left):

    or
    and
    not                      (prefix)
    < <= > >= == !=          (one comparison: ``a < b < c`` is an error, join with ``and``)
    + -
    * /
    -                        (unary minus)
    literal, name, f(args), ( expr )

A name followed by ``(`` is a function call (``if``, ``abs``, ...: ``functions``); any other
name is a reference. Nesting is limited (``MAX_DEPTH``) so a hostile formula cannot exhaust
the stack.
"""

from algotrade.features.expressions.lexer import Token, tokens
from algotrade.features.expressions.nodes import (
    Binary,
    Call,
    ExpressionError,
    Literal,
    Node,
    Ref,
    Unary,
)

MAX_DEPTH = 60
COMPARISONS = frozenset({"<", "<=", ">", ">=", "==", "!="})
_CONSTANTS = {"true": True, "false": False, "null": None}


class _Parser:
    def __init__(self, text: str, where: str) -> None:
        self.toks = tokens(text, where)
        self.i = 0
        self.where = where
        self.depth = 0

    @property
    def tok(self) -> Token:
        return self.toks[self.i]

    def fail(self, message: str, tok: Token | None = None) -> ExpressionError:
        return ExpressionError(self.where, (tok or self.tok).pos, message)

    def take(self) -> Token:
        tok = self.tok
        self.i += 1
        return tok

    def at(self, kind: str, *texts: str) -> bool:
        return self.tok.kind == kind and (not texts or self.tok.text in texts)

    def expect(self, text: str) -> Token:
        if not self.at("op", text):
            found = self.tok.text or "the end"
            raise self.fail(f"expected {text!r}, found {found!r}")
        return self.take()

    def parse(self) -> Node:
        if self.at("end"):
            raise self.fail("empty formula")
        node = self.or_()
        if not self.at("end"):
            raise self.fail(f"unexpected {self.tok.text!r} after a complete expression")
        return node

    def nested(self) -> None:
        self.depth += 1
        if self.depth > MAX_DEPTH:
            raise self.fail(f"nested deeper than {MAX_DEPTH} levels")

    def or_(self) -> Node:
        node = self.and_()
        while self.at("kw", "or"):
            tok = self.take()
            node = Binary("or", node, self.and_(), tok.pos)
        return node

    def and_(self) -> Node:
        node = self.not_()
        while self.at("kw", "and"):
            tok = self.take()
            node = Binary("and", node, self.not_(), tok.pos)
        return node

    def not_(self) -> Node:
        if self.at("kw", "not"):
            tok = self.take()
            self.nested()
            node = Unary("not", self.not_(), tok.pos)
            self.depth -= 1
            return node
        return self.comparison()

    def comparison(self) -> Node:
        node = self.additive()
        if self.at("op") and self.tok.text in COMPARISONS:
            tok = self.take()
            node = Binary(tok.text, node, self.additive(), tok.pos)
            if self.at("op") and self.tok.text in COMPARISONS:
                raise self.fail("compare once per term: write a < b and b < c")
        return node

    def additive(self) -> Node:
        node = self.multiplicative()
        while self.at("op", "+", "-"):
            tok = self.take()
            node = Binary(tok.text, node, self.multiplicative(), tok.pos)
        return node

    def multiplicative(self) -> Node:
        node = self.unary()
        while self.at("op", "*", "/"):
            tok = self.take()
            node = Binary(tok.text, node, self.unary(), tok.pos)
        return node

    def unary(self) -> Node:
        if self.at("op", "-"):
            tok = self.take()
            self.nested()
            node = Unary("-", self.unary(), tok.pos)
            self.depth -= 1
            return node
        return self.primary()

    def primary(self) -> Node:
        tok = self.tok
        if tok.kind in ("num", "str"):
            self.take()
            return Literal(tok.value, tok.pos)
        if tok.kind == "kw" and tok.text in _CONSTANTS:
            self.take()
            return Literal(_CONSTANTS[tok.text], tok.pos)
        if tok.kind == "name":
            self.take()
            if self.at("op", "("):
                return self.call(tok)
            return Ref(tok.text, tok.pos)
        if self.at("op", "("):
            self.take()
            self.nested()
            node = self.or_()
            self.depth -= 1
            self.expect(")")
            return node
        found = tok.text or "the end of the formula"
        raise self.fail(f"expected a value, a name or '(', found {found!r}")

    def call(self, name: Token) -> Node:
        if "." in name.text:
            raise self.fail(f"{name.text!r} is not a function", name)
        self.expect("(")
        self.nested()
        args: list[Node] = []
        if not self.at("op", ")"):
            args.append(self.or_())
            while self.at("op", ","):
                self.take()
                args.append(self.or_())
        self.depth -= 1
        self.expect(")")
        return Call(name.text, tuple(args), name.pos)


def parse_formula(text: str, where: str) -> Node:
    """The syntax tree of ``text``. Raises ``ExpressionError`` naming ``where`` and the position."""
    return _Parser(text, where).parse()
