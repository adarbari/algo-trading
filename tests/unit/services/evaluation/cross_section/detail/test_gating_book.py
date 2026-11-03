"""The portfolio level in the harness (ADR 0088 G15): a gate over ``portfolio.*`` is decided with
the book of the setup's own trades decided at earlier sessions, a session at a time; its stored
legs are never reused."""

from datetime import date
from typing import Any

import pytest

from algotrade.config.user import UserContext
from algotrade.services.evaluation.cross_section import harness, measuring
from algotrade.services.evaluation.cross_section.harness import evaluate_edge
from algotrade.services.evaluation.cross_section.measures import Pick
from algotrade.services.evaluation.cross_section.results import write_edge_eval
from algotrade.services.evaluation.portfolio_level.book import PERSONAL_BOOK
from algotrade.services.evaluation.portfolio_level.trades import trades_of
from algotrade.services.evaluation.portfolio_level.walk import Book
from tests.unit.services.evaluation.cross_section.conftest import (
    AS_OF,
    DAYS,
    World,
    build_world,
    edge,
)

D1, D2, D3, D4 = DAYS[0], DAYS[2], DAYS[4], DAYS[6]  # the decision sessions of horizon 2


def gate(n: int) -> dict[str, Any]:
    return {"all": [{"field": "portfolio.open_positions", "op": "lt", "value": n}]}


def decided(monkeypatch: pytest.MonkeyPatch, w: World, n: int) -> dict[date, str]:
    """The gate states the harness decided with the book, as it hands them to ``tagged``."""
    seen: list[dict[date, str]] = []
    real = harness.tagged

    def spy(found: Any, e: Any, s: Any, decided: Any = None) -> Any:
        seen.append(dict(decided or {}))
        return real(found, e, s, decided)

    monkeypatch.setattr(harness, "tagged", spy)
    e = edge(top_k=3, gate=gate(n))
    evaluate_edge(w.reader, w.results, w.configs, UserContext("site"), e, DAYS[0], DAYS[-1], AS_OF)
    return seen[0]


def test_the_gate_closes_once_two_trades_are_open_and_opens_when_they_exit(
    monkeypatch: pytest.MonkeyPatch, world: World
) -> None:
    # three picks a session: D2 finds D1's three trades open (3 is not < 3), D3 finds none
    # (D1's exited at D2's close, D2's were never taken: its gate was closed)
    assert decided(monkeypatch, world, 3) == {D1: "open", D2: "closed", D3: "open", D4: "closed"}


def test_a_gate_the_book_never_fills_stays_open(
    monkeypatch: pytest.MonkeyPatch, world: World
) -> None:
    assert set(decided(monkeypatch, world, 4).values()) == {"open"}


def test_the_decided_states_do_not_depend_on_the_chunk_size(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(measuring, "CHUNK_SESSIONS", 1)
    one = decided(monkeypatch, build_world(), 3)
    monkeypatch.setattr(measuring, "CHUNK_SESSIONS", 50)
    assert decided(monkeypatch, build_world(), 3) == one


def test_a_stored_leg_of_an_in_order_edge_is_never_reused(world: World) -> None:
    user, e = UserContext("site"), edge(top_k=3, gate=gate(3))
    first = evaluate_edge(world.reader, world.results, world.configs, user, e, D1, DAYS[-1], AS_OF)
    write_edge_eval(world.results, first, AS_OF)
    again = evaluate_edge(world.reader, world.results, world.configs, user, e, D1, DAYS[-1], AS_OF)
    assert (again.mode, again.legs_reused) == ("full", 0)
    assert again.legs_computed == first.legs_computed


def test_a_personal_trade_in_the_book_leaves_every_field_unknown() -> None:
    book = Book()
    pick = Pick("EQ:A", 1, "", exit_session=date(2026, 9, 9), outcome_licence="personal")
    book.add(trades_of([pick], D1, 2))
    row = book.row_at(D2, lambda _d, ids: dict.fromkeys(ids, "Tech"))
    assert row.reason == PERSONAL_BOOK
    assert set(row.values.values()) == {None}
    assert measuring._row_at(None, None, D2) is None  # type: ignore[arg-type]
