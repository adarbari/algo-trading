"""Value types, null handling and the built-in functions of the expression language.

A value is a column (numpy array, one element per row) of one of four types, each with its
own null:

    num    float64, NaN is null          (feature dtypes float, float32, int)
    bool   float64 1.0 / 0.0, NaN null   (three-valued: true, false, unknown)
    str    object, None is null          (a label / category, or text)
    date   datetime64[ns], NaT is null

``null`` (the literal) has type ``null`` until it meets another type. Null is UNKNOWN: it
propagates through arithmetic, comparisons and functions; ``and`` / ``or`` are Kleene
(``false and null`` is false, ``true or null`` is true); ``if(null, a, b)`` is null; a division
by zero, ``log`` of a value <= 0, ``sqrt`` of a negative and any non-finite result are null.

Built-ins (``FUNCTIONS``): ``if(cond, a, b)``, ``abs(x)``, ``min(a, b, ...)``,
``max(a, b, ...)`` (numbers or strings; null if any is null), ``log(x)`` (natural),
``sqrt(x)``, ``ncdf(x)`` (the standard normal CDF, for a probit: ``ncdf(b0 + b1 * x)``),
``clip(x, lo, hi)``, ``coalesce(a, b, ...)`` (the first non-null),
``is_null(x)`` (never null), ``one_of(x, "A", "B", ...)`` (x equals one of the literals) and
``exists(group)`` (the instrument has a row in that group for the session: false when the
group has rows for the session but not this instrument, null when it has none at all).
"""

import operator
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np

from algotrade.quant.black_scholes import norm_cdf

KINDS = ("num", "bool", "str", "date")
_NULLS = {"num": np.nan, "bool": np.nan, "str": None, "date": np.datetime64("NaT", "ns")}
_DTYPES: dict[str, np.dtype[Any]] = {
    "num": np.dtype(np.float64),
    "bool": np.dtype(np.float64),
    "str": np.dtype(object),
    "date": np.dtype("datetime64[ns]"),
}


@dataclass(frozen=True)
class Type:
    """A value type; ``categories``: the closed set a ``str`` can take (``None``: open)."""

    kind: str  # one of KINDS, or "null"
    categories: frozenset[str] | None = None

    def __str__(self) -> str:
        if self.kind == "str" and self.categories is not None:
            return f"str (one of {', '.join(sorted(self.categories))})"
        return self.kind


NUM, BOOL, DATE, NULL = Type("num"), Type("bool"), Type("date"), Type("null")
OPEN_STR = Type("str")


def unify(types: Sequence[Type]) -> Type | None:
    """The common type of branches (``null`` fits any), or ``None`` when they differ."""
    kinds = {t.kind for t in types} - {"null"}
    if not kinds:
        return NULL
    if len(kinds) > 1:
        return None
    kind = kinds.pop()
    if kind != "str":
        return Type(kind)
    cats = [t.categories for t in types if t.kind == "str"]
    if any(c is None for c in cats):
        return OPEN_STR
    return Type("str", frozenset().union(*(c for c in cats if c is not None)))


def full(value: object, kind: str, n: int) -> np.ndarray:
    """A column of ``n`` copies of ``value`` (``None``: null) as type ``kind``."""
    if kind == "null":
        kind = "num"
    if value is None:
        value = _NULLS[kind]
    elif kind == "bool":
        value = 1.0 if value else 0.0
    out = np.empty(n, dtype=_DTYPES[kind])
    out[:] = value
    return out


def null_mask(values: np.ndarray, kind: str) -> np.ndarray:
    if kind in ("num", "bool", "null"):
        return np.isnan(values)
    if kind == "date":
        return np.isnat(values)
    return np.array([v is None for v in values], dtype=bool)


def as_kind(values: np.ndarray, current: str, kind: str) -> np.ndarray:
    """A ``null``-typed column as an all-null column of ``kind`` (other columns as they are)."""
    return full(None, kind, len(values)) if current == "null" else values


def truth(mask: np.ndarray, unknown: np.ndarray) -> np.ndarray:
    """A bool column from a boolean ``mask``, null where ``unknown``."""
    return np.where(unknown, np.nan, mask.astype(np.float64))


def _filled(values: np.ndarray, kind: str, nulls: np.ndarray) -> np.ndarray:
    """``values`` with nulls replaced by a harmless value (results there are masked)."""
    if kind == "str":
        return np.where(nulls, "", values)
    if kind == "date":
        return np.where(nulls, np.datetime64(0, "ns"), values)
    return np.where(nulls, 0.0, values)


COMPARE: dict[str, Callable[[Any, Any], Any]] = {
    "<": operator.lt,
    "<=": operator.le,
    ">": operator.gt,
    ">=": operator.ge,
    "==": operator.eq,
    "!=": operator.ne,
}


def compare(op: str, a: np.ndarray, b: np.ndarray, kind: str) -> np.ndarray:
    """``a op b`` elementwise (``op`` in < <= > >= == !=); null where either is null."""
    nulls = null_mask(a, kind) | null_mask(b, kind)
    x, y = _filled(a, kind, nulls), _filled(b, kind, nulls)
    result = COMPARE[op](x, y)
    return truth(np.asarray(result, dtype=bool), nulls)


def finite(values: np.ndarray) -> np.ndarray:
    """Non-finite results (overflow, inf) are null."""
    return np.where(np.isfinite(values), values, np.nan)


def arithmetic(op: str, a: np.ndarray, b: np.ndarray) -> np.ndarray:
    with np.errstate(all="ignore"):
        if op == "+":
            return finite(a + b)
        if op == "-":
            return finite(a - b)
        if op == "*":
            return finite(a * b)
        return finite(np.where(b == 0, np.nan, a / np.where(b == 0, 1.0, b)))


def kleene_and(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    false = (a == 0) | (b == 0)
    return np.where(false, 0.0, np.where(np.isnan(a) | np.isnan(b), np.nan, 1.0))


def kleene_or(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    true = (a == 1) | (b == 1)
    return np.where(true, 1.0, np.where(np.isnan(a) | np.isnan(b), np.nan, 0.0))


# --------------------------------------------------------------------------- built-ins
type Args = Sequence[np.ndarray]


def _if(args: Args, kinds: Sequence[str], out: str) -> np.ndarray:
    cond, a, b = args[0], as_kind(args[1], kinds[1], out), as_kind(args[2], kinds[2], out)
    picked = np.where(cond == 1, a, b)
    return np.where(np.isnan(cond), full(None, out, len(cond)), picked).astype(_DTYPES[out])


type Body = Callable[[Args, Sequence[str], str], np.ndarray]


def _extreme(pick: Callable[[np.ndarray, np.ndarray], np.ndarray]) -> Body:
    def apply(args: Args, kinds: Sequence[str], out: str) -> np.ndarray:
        cols = [as_kind(a, k, out) for a, k in zip(args, kinds, strict=True)]
        nulls = np.logical_or.reduce([null_mask(c, out) for c in cols])
        result = _filled(cols[0], out, nulls)
        for col in cols[1:]:
            result = pick(result, _filled(col, out, nulls))
        return np.where(nulls, full(None, out, len(nulls)), result).astype(_DTYPES[out])

    return apply


def _coalesce(args: Args, kinds: Sequence[str], out: str) -> np.ndarray:
    result = as_kind(args[0], kinds[0], out).copy()
    for col, kind in zip(args[1:], kinds[1:], strict=True):
        gaps = null_mask(result, out)
        result = np.where(gaps, as_kind(col, kind, out), result).astype(_DTYPES[out])
    return result


def _is_null(args: Args, kinds: Sequence[str], out: str) -> np.ndarray:
    return null_mask(args[0], kinds[0]).astype(np.float64)


def _one_of(args: Args, kinds: Sequence[str], out: str) -> np.ndarray:
    x, kind = args[0], kinds[0]
    nulls = null_mask(x, kind)
    hits = np.zeros(len(x), dtype=bool)
    for value in args[1:]:
        hits |= np.asarray(_filled(x, kind, nulls) == value, dtype=bool)
    return truth(hits, nulls)


def _numeric(
    fn: Callable[[np.ndarray], np.ndarray], valid: Callable[[np.ndarray], np.ndarray]
) -> Body:
    def apply(args: Args, kinds: Sequence[str], out: str) -> np.ndarray:
        x = args[0]
        with np.errstate(all="ignore"):
            return finite(np.where(valid(x), fn(np.where(valid(x), x, 1.0)), np.nan))

    return apply


def _clip(args: Args, kinds: Sequence[str], out: str) -> np.ndarray:
    x, lo, hi = args
    nulls = np.isnan(x) | np.isnan(lo) | np.isnan(hi)
    return np.where(nulls, np.nan, np.minimum(np.maximum(x, lo), hi))


@dataclass(frozen=True)
class Function:
    """A built-in: argument count (``variadic``: at least ``arity``) and its vectorised body
    ``apply(args, arg_kinds, result_kind)``. Type rules: ``checker``."""

    name: str
    arity: int
    apply: Callable[[Args, Sequence[str], str], np.ndarray]
    variadic: bool = False


FUNCTIONS: dict[str, Function] = {
    f.name: f
    for f in (
        Function("if", 3, _if),
        Function("abs", 1, _numeric(np.abs, lambda x: ~np.isnan(x))),
        Function("sqrt", 1, _numeric(np.sqrt, lambda x: x >= 0)),
        Function("log", 1, _numeric(np.log, lambda x: x > 0)),
        Function("ncdf", 1, _numeric(norm_cdf, lambda x: ~np.isnan(x))),
        Function("min", 2, _extreme(np.minimum), variadic=True),
        Function("max", 2, _extreme(np.maximum), variadic=True),
        Function("clip", 3, _clip),
        Function("coalesce", 2, _coalesce, variadic=True),
        Function("is_null", 1, _is_null),
        Function("one_of", 2, _one_of, variadic=True),
        Function("exists", 1, lambda args, kinds, out: args[0]),
    )
}
