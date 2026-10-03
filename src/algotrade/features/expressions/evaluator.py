"""Evaluate a checked formula over columns, vectorised: one pass per node over every row.

``evaluate_formula(node, lookup, n)`` returns the result column (``functions`` describes the four
value types and their nulls). ``lookup(name)`` returns a name's column and type kind: a stored
feature (``group.column``), an already evaluated expression feature, or ``exists:<group>``
for ``exists(group)``. Rows are independent, so the same code evaluates one session (one row
per instrument) or a date range (one row per instrument and session).

``to_column`` / ``from_column`` convert between pandas columns of a feature's dtype and the
evaluation types.
"""

from collections.abc import Callable

import numpy as np
import pandas as pd

from algotrade.features.expressions.checker import literal_type
from algotrade.features.expressions.functions import (
    FUNCTIONS,
    Type,
    arithmetic,
    as_kind,
    compare,
    full,
    kleene_and,
    kleene_or,
    unify,
)
from algotrade.features.expressions.nodes import Binary, Call, Literal, Node, Ref, Unary

type Lookup = Callable[[str], tuple[np.ndarray, str]]
# Feature dtype -> evaluation kind.
KIND_OF = {"float": "num", "float32": "num", "int": "num", "bool": "bool", "str": "str",
           "date": "date"}  # fmt: skip


def to_column(values: pd.Series | np.ndarray, kind: str) -> np.ndarray:
    """A stored column (any pandas / Arrow dtype, nulls as NaN / NA / None) as ``kind``."""
    series = pd.Series(values)
    if kind == "num":
        return pd.to_numeric(series, errors="coerce").to_numpy(dtype=np.float64, na_value=np.nan)
    if kind == "bool":
        return series.map({True: 1.0, False: 0.0}).to_numpy(dtype=np.float64, na_value=np.nan)
    if kind == "date":
        return pd.to_datetime(series).to_numpy(dtype="datetime64[ns]")
    out = series.astype(object).to_numpy(copy=True)
    out[series.isna().to_numpy()] = None
    return out


def from_column(values: np.ndarray, kind: str) -> pd.Series:
    """An evaluated column as a plain pandas column (bool: Arrow-backed, nulls kept)."""
    if kind == "bool":
        flags = pd.Series(values == 1).astype("bool[pyarrow]")
        return flags.mask(np.isnan(values))
    return pd.Series(values)


def evaluate_formula(node: Node, lookup: Lookup, n: int) -> tuple[np.ndarray, str]:
    """``node`` over ``n`` rows -> (column, kind). ``node`` must have passed ``checker``."""
    if isinstance(node, Literal):
        kind = literal_type(node.value).kind
        return full(node.value, kind, n), kind
    if isinstance(node, Ref):
        return lookup(node.name)
    if isinstance(node, Unary):
        values, kind = evaluate_formula(node.operand, lookup, n)
        if node.op == "-":
            return -as_kind(values, kind, "num"), "num"
        bools = as_kind(values, kind, "bool")
        return np.where(np.isnan(bools), np.nan, 1.0 - bools), "bool"
    if isinstance(node, Binary):
        return _binary(node, lookup, n)
    return _call(node, lookup, n)


def _binary(node: Binary, lookup: Lookup, n: int) -> tuple[np.ndarray, str]:
    a, ka = evaluate_formula(node.left, lookup, n)
    b, kb = evaluate_formula(node.right, lookup, n)
    if node.op in ("+", "-", "*", "/"):
        return arithmetic(node.op, as_kind(a, ka, "num"), as_kind(b, kb, "num")), "num"
    if node.op in ("and", "or"):
        x, y = as_kind(a, ka, "bool"), as_kind(b, kb, "bool")
        return (kleene_and(x, y) if node.op == "and" else kleene_or(x, y)), "bool"
    return compare(node.op, a, b, ka), "bool"


def _call(node: Call, lookup: Lookup, n: int) -> tuple[np.ndarray, str]:
    if node.func == "exists":
        arg = node.args[0]
        assert isinstance(arg, Ref)
        return lookup(f"exists:{arg.name}")
    evaluated = [evaluate_formula(a, lookup, n) for a in node.args]
    args = [v for v, _ in evaluated]
    kinds = [k for _, k in evaluated]
    if node.func in ("is_null", "one_of"):
        out = "bool"
    elif node.func in ("if", "coalesce", "min", "max"):
        branches = kinds[1:] if node.func == "if" else kinds
        common = unify([Type(k) for k in branches])
        out = "num" if common is None or common.kind == "null" else common.kind
    else:
        out = "num"
    if node.func == "one_of":  # the literals as values, not columns
        literals = [a.value for a in node.args[1:] if isinstance(a, Literal)]
        args = [args[0], *(np.asarray(v, dtype=object) for v in literals)]
    return FUNCTIONS[node.func].apply(args, kinds, out), out
