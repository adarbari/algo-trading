"""The base of an edge is not gated on the screener's own signal (a fitness test over
``config/site/edges``): picks that equal their base score a lift of about 0 and make a
retire rule that cannot fire. A universe gate that selects on a field the edge's screener
hard-filters on, at the same or a tighter value (a boolean flag equal to the screener's
criterion), is that tautology; a ``not_null`` gate or a bound far looser than the criterion
is the legitimate coverage gate of a sparse score."""

import tomllib
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from tests.conftest import REPO_ROOT

SITE = REPO_ROOT / "config" / "site"
SHARED_PREFIXES = ("instrument.", "rollup.price_stats@")  # the site base gates, not a signal
COVERAGE_OPS = ("not_null",)
# edge -> why its universe may select on a field its screener also uses
PRESENCE = "the gate is a presence bound the screener repeats (no stored value fails it)"
KNOWN_EXCEPTIONS: dict[str, str] = {
    "dual_class_spread_reversion": "PAIRED is structural (a name with no sibling has no spread); "
    "the signal ranked is the spread z-score, not the pairing",
    "idiosyncratic_volatility_and_max": PRESENCE,
    "news_conditioned_reversal": PRESENCE,
    "short_term_momentum_high_turnover": PRESENCE,
}


def load(path: Path) -> dict[str, Any]:
    return tomllib.loads(path.read_text())


def conditions(where: Any) -> Iterator[dict[str, Any]]:
    """The leaf conditions every row must pass: those under ``all`` (an ``any`` / ``not``
    group does not hard-gate)."""
    if isinstance(where, dict) and "field" in where:
        yield where
    elif isinstance(where, dict):
        for child in where.get("all", []):
            yield from conditions(child)


def universe_gates(edge: dict[str, Any]) -> list[dict[str, Any]]:
    """The selective (not coverage) gates of the edge's universe."""
    universe = edge["universe"]
    where = (
        load(SITE / "presets" / "selections" / f"{universe}.toml")["where"]
        if isinstance(universe, str)
        else universe["where"]
    )
    return [c for c in conditions(where) if c["op"] not in COVERAGE_OPS]


def screener_criteria(screener: str) -> list[dict[str, Any]]:
    """The hard, selective criteria of every version of a screener, minus the site base gates."""
    out: list[dict[str, Any]] = []
    for path in sorted((SITE / "presets" / "screeners" / screener).glob("v*.toml")):
        for c in load(path).get("criteria", {}).values():
            hard = c.get("mode", "hard") == "hard" and c["op"] not in COVERAGE_OPS
            if hard and not c["field"].startswith(SHARED_PREFIXES):
                out.append(c)
    return out


def implies(gate: dict[str, Any], criterion: dict[str, Any]) -> bool:
    """Whether every row passing ``gate`` passes ``criterion``: the same field, an equal
    ``eq`` / ``in`` value, or a bound at least as tight. A bound far looser than the criterion
    (``gte -10000`` beside ``gte 5``) is a presence gate, not the signal."""
    if gate["field"] != criterion["field"]:
        return False
    g, c = gate["op"], criterion["op"]
    if g in ("eq", "in") and c == g:
        return bool(gate["value"] == criterion["value"])
    if g in ("gt", "gte") and c in ("gt", "gte"):
        return bool(gate["value"] >= criterion["value"])
    if g in ("lt", "lte") and c in ("lt", "lte"):
        return bool(gate["value"] <= criterion["value"])
    return False


EDGES = {p.parent.name: load(p) for p in sorted((SITE / "edges").glob("*/edge.toml"))}
# a base other than the universe (an event, the out-of-window stretches, a benchmark) is not
# the set the picks are drawn from
ON_UNIVERSE = {i: e for i, e in EDGES.items() if e.get("base", "universe") == "universe"}


def tautologies(edge: dict[str, Any]) -> set[str]:
    gates = universe_gates(edge)
    return {
        g["field"]
        for s in edge.get("screeners", [])
        for c in screener_criteria(s)
        for g in gates
        if implies(g, c)
    }


@pytest.mark.parametrize("edge_id", sorted(ON_UNIVERSE))
def test_a_universe_does_not_gate_on_its_screeners_own_signal(edge_id: str) -> None:
    if edge_id in KNOWN_EXCEPTIONS:
        pytest.skip(KNOWN_EXCEPTIONS[edge_id])
    assert not tautologies(ON_UNIVERSE[edge_id]), (
        f"{edge_id}: the universe selects on a field its screener ranks or filters on, so the "
        "picks equal the base (lift about 0, a retire rule that cannot fire). Gate the base on "
        "coverage (not_null) only, or make the base an event / out_of_window set "
        "(.claude/skills/add-screener, edge-document checklist)."
    )


def test_the_check_flags_a_boolean_gate_equal_to_the_criterion() -> None:
    edge = {"universe": {"where": {"all": [{"field": "feature.flag", "op": "eq", "value": True}]}}}
    flag = {"field": "feature.flag", "op": "eq", "value": True}
    assert universe_gates(edge) == [flag]
    assert implies(flag, {**flag})
    assert not implies(
        {"field": "feature.s", "op": "gte", "value": -10000},
        {"field": "feature.s", "op": "gte", "value": 5},
    )
    coverage = {"universe": {"where": {"all": [{"field": "feature.s", "op": "not_null"}]}}}
    assert universe_gates(coverage) == []


def test_known_exceptions_are_edges_that_still_trip_the_check() -> None:
    assert all(i in ON_UNIVERSE and tautologies(ON_UNIVERSE[i]) for i in KNOWN_EXCEPTIONS)
