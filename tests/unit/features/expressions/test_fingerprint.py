"""The formula fingerprint: the same formula written differently gives one fingerprint, a
different formula another; ``find_duplicate`` looks in the site's features, then the user's."""

import itertools

import pytest

from algotrade.config.site.features.definitions import FeatureDefinition
from algotrade.features.expressions.fingerprint import find_duplicate, fingerprint
from algotrade.features.expressions.nodes import ExpressionError


def d(expr: str, name: str = "f", **params: float) -> FeatureDefinition:
    return FeatureDefinition(
        name=name,
        theme="t",
        expr=expr,
        dtype="float",
        unit="ratio",
        description="x",
        null_meaning="x",
        params=params,
    )


def same(a: str, b: str) -> bool:
    return fingerprint(d(a)).hash == fingerprint(d(b)).hash


def test_the_plan_example_is_one_formula() -> None:
    assert same("close/price_stats.high_52w - 1", "-1 + close / price_stats.high_52w")


def test_whitespace_and_redundant_parentheses_are_irrelevant() -> None:
    assert same("a+b*c", " ( a ) +( ( b*c ) )")


def test_the_hash_is_short_and_stable() -> None:
    got = fingerprint(d("a + b"))
    assert got.text == "(+ a b)" and len(got.hash) == 12
    assert got == fingerprint(d("b + a"))


@pytest.mark.parametrize("op", ["+", "*", "==", "!=", "and", "or"])
def test_commutative_operators_reorder(op: str) -> None:
    assert same(f"a.x {op} b.y", f"b.y {op} a.x")


@pytest.mark.parametrize("func", ["min", "max"])
def test_min_and_max_ignore_argument_order(func: str) -> None:
    names = ["a.x", "b.y", "c.z"]
    prints = {fingerprint(d(f"{func}({', '.join(p)})")).hash for p in itertools.permutations(names)}
    assert len(prints) == 1


def test_every_ordering_of_a_sum_and_a_product_matches() -> None:
    for op in ("+", "*"):
        prints = {
            fingerprint(d(f" {op} ".join(p))).hash
            for p in itertools.permutations(["a.x", "b.y", "c.z", "2"])
        }
        assert len(prints) == 1


def test_order_is_kept_where_it_matters() -> None:
    assert not same("a.x - b.y", "b.y - a.x")
    assert not same("a.x / b.y", "b.y / a.x")
    assert not same("if(a.x > 1, 2, 3)", "if(a.x > 1, 3, 2)")


def test_a_threshold_written_either_way_matches() -> None:
    assert same("a.x > 5", "5 < a.x")
    assert same("a.x >= 5", "5 <= a.x")
    assert not same("a.x > 5", "a.x < 5")


def test_constants_are_folded() -> None:
    assert same("a.x * (2 * 3)", "6 * a.x")
    assert same("a.x + 1 + 2", "3 + a.x")
    assert same("-(1) + a.x", "a.x - 1")
    assert same("a.x + 0", "a.x")
    assert same("a.x and not false", "true and a.x")


def test_params_are_substituted() -> None:
    with_param = fingerprint(d("a.x > cut", cut=2.0))
    assert with_param == fingerprint(d("a.x > 2"))
    assert with_param != fingerprint(d("a.x > cut", cut=3.0))


def test_different_formulas_differ() -> None:
    assert not same("a.x + b.y", "a.x * b.y")
    assert not same("a.x", "a.y")
    assert not same("a.x > 1", "a.x > 1.5")


def test_the_documented_limit_algebra_is_not_recognised() -> None:
    assert not same("(a.x - a.y) / a.y", "a.x / a.y - 1")


def test_an_invalid_formula_raises() -> None:
    with pytest.raises(ExpressionError):
        fingerprint(d("a.x +"))


def test_find_duplicate_prefers_the_site_then_the_users_own() -> None:
    wanted = fingerprint(d("b.y + a.x"))
    site = [d("a.x * 2", "twice"), d("a.x + b.y", "site_sum")]
    mine = [d("a.x + b.y", "my_sum")]
    assert find_duplicate(wanted, site, mine) == "site_sum"
    assert find_duplicate(wanted, site[:1], mine) == "my_sum"
    assert find_duplicate(wanted, site[:1], []) is None


def test_find_duplicate_skips_a_definition_that_does_not_parse() -> None:
    wanted = fingerprint(d("a.x"))
    assert find_duplicate(wanted, [d("(((", "broken")], [d("a.x", "ok")]) == "ok"
