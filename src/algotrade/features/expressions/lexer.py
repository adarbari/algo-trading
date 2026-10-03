"""Split a formula into tokens, each with its position.

Tokens: numbers (``10``, ``0.25``, ``1e6``, ``100_000``), strings (``"HIGH"`` or ``'HIGH'``;
``\\`` escapes the quote or a backslash), names (``price_stats.hv30``, ``near_52w``, ``abs``:
lower-case letters, digits and ``_``, at most one ``.``), the keywords ``and or not true false
null``, operators ``+ - * / < <= > >= == !=``, ``( ) ,``. ``#`` starts a comment to the end of
the line. Anything else (``__import__``, ``;``, ``[``, a backtick, ``=``) is an error at its
position: the language has no attribute access, indexing, assignment or Python names.
"""

import re
from dataclasses import dataclass

from algotrade.features.expressions.nodes import ExpressionError, Pos

MAX_LENGTH = 4000  # characters in one formula
KEYWORDS = frozenset({"and", "or", "not", "true", "false", "null"})
OPERATORS = ("<=", ">=", "==", "!=", "<", ">", "+", "-", "*", "/", "(", ")", ",")
_NUMBER = re.compile(r"(\d+(_\d+)*)(\.\d+(_\d+)*)?([eE][+-]?\d+)?")
_NAME = re.compile(r"[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)?")


@dataclass(frozen=True)
class Token:
    kind: str  # "num", "str", "name", "kw", "op", "end"
    text: str
    pos: Pos
    value: float | str | None = None


def _string(text: str, start: int, where: str, pos: Pos) -> tuple[str, int]:
    """The string literal starting at ``text[start]`` (a quote) -> (value, end index)."""
    quote, i, out = text[start], start + 1, []
    while i < len(text):
        ch = text[i]
        if ch == "\\" and i + 1 < len(text) and text[i + 1] in (quote, "\\"):
            out.append(text[i + 1])
            i += 2
            continue
        if ch == quote:
            return "".join(out), i + 1
        if ch == "\n":
            break
        out.append(ch)
        i += 1
    raise ExpressionError(where, pos, "unterminated string")


def _number(text: str, i: int, where: str, pos: Pos) -> tuple[Token, int]:
    match = _NUMBER.match(text, i)
    if match is None or text[i] == ".":
        raise ExpressionError(where, pos, "a number starts with a digit: write 0.5")
    end = match.end()
    if end < len(text) and (text[end].isalnum() or text[end] in "._"):
        raise ExpressionError(where, pos, f"malformed number {text[i : end + 1]!r}")
    return Token("num", match.group(), pos, float(match.group().replace("_", ""))), end


def _word(text: str, i: int, where: str, pos: Pos) -> tuple[Token, int] | None:
    match = _NAME.match(text, i)
    if match is None:
        return None
    word, end = match.group(), match.end()
    if end < len(text) and (text[end].isalnum() or text[end] in "._"):
        raise ExpressionError(where, pos, f"invalid name starting {word!r}")
    return Token("kw" if word in KEYWORDS else "name", word, pos, word), end


def _operator(text: str, i: int, where: str, pos: Pos) -> tuple[Token, int]:
    op = next((o for o in OPERATORS if text.startswith(o, i)), None)
    if op is None:
        ch = text[i]
        hint = " (names are lower case)" if ch.isalpha() or ch == "_" else ""
        raise ExpressionError(where, pos, f"unexpected character {ch!r}{hint}")
    return Token("op", op, pos), i + len(op)


def tokens(text: str, where: str) -> list[Token]:
    """``text`` as tokens, ending with an ``end`` token. Raises ``ExpressionError``."""
    if len(text) > MAX_LENGTH:
        raise ExpressionError(where, None, f"formula longer than {MAX_LENGTH} characters")
    out: list[Token] = []
    i, line, line_start = 0, 1, 0
    while i < len(text):
        ch = text[i]
        pos = Pos(line, i - line_start + 1)
        if ch == "\n":
            i, line, line_start = i + 1, line + 1, i + 1
            continue
        if ch in " \t\r":
            i += 1
            continue
        if ch == "#":
            end = text.find("\n", i)
            i = len(text) if end < 0 else end
            continue
        if ch in "\"'":
            value, i = _string(text, i, where, pos)
            out.append(Token("str", value, pos, value))
            continue
        if ch.isdigit() or (ch == "." and text[i + 1 : i + 2].isdigit()):
            tok, i = _number(text, i, where, pos)
        else:
            tok, i = _word(text, i, where, pos) or _operator(text, i, where, pos)
        out.append(tok)
    out.append(Token("end", "", Pos(line, i - line_start + 1)))
    return out
