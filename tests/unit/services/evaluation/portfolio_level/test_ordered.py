"""``in_order``: an edge is walked in order when a gate, a variant's gate, an entry condition or a
case value names a field of an in-order level, whichever rule site it sits at (ADR 0088, G15)."""

from dataclasses import replace
from types import SimpleNamespace

import pytest

from algotrade.config.edges.positions.cases import Case, CaseValue, EntrySpec
from algotrade.config.strategy.levels import LEVELS, level_of_field
from algotrade.core.model.predicates import Group, Rule
from algotrade.services.evaluation.portfolio_level.ordered import in_order
from tests.unit.services.evaluation.cross_section.conftest import edge

BOOK = Group("all", (Rule("portfolio.open_positions", "lt", 3),))
PLAIN = Group("all", (Rule("market.vix@v1.close", "lt", 30),))


def test_an_edge_naming_no_book_field_is_not_in_order() -> None:
    assert not in_order(edge())
    assert not in_order(replace(edge(), gate=PLAIN))


def test_the_edge_gate_decides() -> None:
    assert in_order(replace(edge(), gate=BOOK))


def test_a_variant_gate_decides() -> None:
    base = edge()
    sleeve = SimpleNamespace(gate=BOOK, outcome=base.outcome)
    assert in_order(replace(base, variants=(sleeve,)))  # type: ignore[arg-type]


def test_an_entry_condition_decides() -> None:
    base = edge()
    entry = EntrySpec(BOOK, 2)
    assert in_order(replace(base, outcome=replace(base.outcome, entry=entry)))


def test_a_case_value_decides() -> None:
    base = edge()
    position = SimpleNamespace(cases=(CaseValue("n", (Case(BOOK, 1),), 0),))
    assert in_order(replace(base, outcome=replace(base.outcome, position=position)))  # type: ignore[arg-type]


@pytest.mark.parametrize("name", ["portfolio.open_positions", "portfolio.max_name_share"])
def test_it_is_driven_by_the_level_table(name: str) -> None:
    level = level_of_field(name)
    assert level is not None and level.in_order
    assert [lv.key for lv in LEVELS if lv.in_order] == ["portfolio"]


def test_a_field_no_level_claims_has_no_level() -> None:
    assert level_of_field("nonsense.x") is None
    assert not level_of_field("market.vix@v1.close").in_order  # type: ignore[union-attr]
