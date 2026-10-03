"""Property tests for the expression language: algebraic identities hold on random columns
with nulls, and three-valued logic obeys De Morgan's laws (ADR 0023 step 3)."""

import numpy as np
from hypothesis import given
from hypothesis import strategies as st

from algotrade.features.expressions.evaluator import evaluate_formula
from algotrade.features.expressions.parser import parse_formula

N = 12
numbers = st.lists(
    st.one_of(st.none(), st.floats(-1e6, 1e6, allow_nan=False)), min_size=N, max_size=N
)
truths = st.lists(st.sampled_from([None, True, False]), min_size=N, max_size=N)


def column(values: list[object]) -> np.ndarray:
    return np.array([np.nan if v is None else float(v) for v in values])  # type: ignore[arg-type]


def run(text: str, **cols: tuple[np.ndarray, str]) -> np.ndarray:
    values, _ = evaluate_formula(parse_formula(text, "p"), lambda n: cols[n.replace("g.", "")], N)
    return values


def same(a: np.ndarray, b: np.ndarray, tol: float = 0.0) -> bool:
    nulls = np.isnan(a)
    return bool((nulls == np.isnan(b)).all() and np.allclose(a[~nulls], b[~nulls], atol=tol))


@given(x=numbers, y=numbers)
def test_arithmetic_identities(x: list[object], y: list[object]) -> None:
    cols = {"x": (column(x), "num"), "y": (column(y), "num")}
    assert same(run("g.x + g.y", **cols), run("g.y + g.x", **cols))
    assert same(run("g.x * 1", **cols), column(x))
    assert same(run("g.x - g.x", **cols), np.where(np.isnan(column(x)), np.nan, 0.0))
    assert same(run("-(-g.x)", **cols), column(x))
    assert (run("abs(g.x)", **cols)[~np.isnan(column(x))] >= 0).all()
    clipped = run("clip(g.x, -1, 1)", **cols)
    assert (np.abs(clipped[~np.isnan(clipped)]) <= 1).all()
    ratio = run("g.x / g.y", **cols)
    y_values = column(y)
    assert np.isnan(ratio[y_values == 0]).all()  # division by zero is null, never inf
    ok = ~np.isnan(ratio) & (np.abs(y_values) > 1e-3)
    assert np.allclose((ratio * y_values)[ok], column(x)[ok], rtol=1e-9, atol=1e-6)


@given(x=numbers, y=numbers)
def test_null_handling(x: list[object], y: list[object]) -> None:
    cols = {"x": (column(x), "num"), "y": (column(y), "num")}
    both_null = np.isnan(column(x)) & np.isnan(column(y))
    assert (np.isnan(run("coalesce(g.x, g.y)", **cols)) == both_null).all()
    any_null = np.isnan(column(x)) | np.isnan(column(y))
    assert (np.isnan(run("g.x + g.y", **cols)) == any_null).all()
    assert (np.isnan(run("g.x < g.y", **cols)) == any_null).all()
    assert (run("is_null(g.x)", **cols) == np.isnan(column(x))).all()
    assert same(run("max(g.x, g.y)", **cols), run("-min(-g.x, -g.y)", **cols))


@given(a=truths, b=truths, x=numbers)
def test_three_valued_logic(a: list[object], b: list[object], x: list[object]) -> None:
    cols = {"a": (column(a), "bool"), "b": (column(b), "bool"), "x": (column(x), "num")}
    assert same(run("not (g.a and g.b)", **cols), run("not g.a or not g.b", **cols))
    assert same(run("not (g.a or g.b)", **cols), run("not g.a and not g.b", **cols))
    assert same(run("not not g.a", **cols), column(a))
    assert same(run("g.a and g.b", **cols), run("g.b and g.a", **cols))
    picked = run("if(g.a, g.x, g.x)", **cols)
    assert same(picked, np.where(np.isnan(column(a)), np.nan, column(x)))
