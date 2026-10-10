"""``SessionReads``: scopes sharing one universe read the eligible names once, the implied vol is
read once per (field, names, session) and a scope's scored outcomes once per (scope, horizon,
session) until the chunk is released."""

from datetime import date
from typing import Any

import pytest

from algotrade.config.strategy.schema import parse_selection
from algotrade.services.evaluation.cross_section import picks
from algotrade.services.evaluation.cross_section.harness import (
    _Measured,
    _Plan,
    _read_closed,
    _Scope,
)
from algotrade.services.evaluation.cross_section.reads import session as session_reads
from algotrade.services.evaluation.cross_section.reads.session import SessionReads
from algotrade.services.evaluation.cross_section.sessions import Leg
from tests.unit.services.evaluation.cross_section.conftest import (
    ACTIVE,
    AS_OF,
    DAYS,
    World,
    build_world,
    edge,
)


def test_scopes_with_one_universe_read_it_once(world: World, monkeypatch: Any) -> None:
    reads: list[date] = []
    real = picks.fields_view

    def counting(reader: Any, fields: Any, day: date, *a: Any, **k: Any) -> Any:
        reads.append(day)
        return real(reader, fields, day, *a, **k)

    monkeypatch.setattr(picks, "fields_view", counting)
    session = SessionReads(world.reader, "label")
    same = [parse_selection(ACTIVE, "active") for _ in range(3)]  # equal, not identical
    got = [session.eligible(u, DAYS[0]) for u in same]
    assert got[0] == got[1] == got[2] and got[0] and reads == [DAYS[0]]
    session.release()
    assert not session._eligible


def test_implied_and_outcomes_are_computed_once_until_release(
    world: World, monkeypatch: Any
) -> None:
    calls: list[tuple[str, date]] = []

    def fake(reader: Any, field: str, ids: Any, day: date) -> dict[str, float | None]:
        calls.append((field, day))
        return dict.fromkeys(ids, 1.0)

    monkeypatch.setattr(session_reads, "implied_at", fake)
    session = SessionReads(world.reader, "label")
    ids = frozenset({"a", "b"})
    for _ in range(2):
        session.implied("f", ids, DAYS[0])
    session.implied("f", frozenset({"a"}), DAYS[0])
    assert len(calls) == 2
    scored: list[int] = []
    for _ in range(3):
        session.outcomes("main", 20, DAYS[0], lambda: scored.append(1) or None)  # type: ignore[arg-type,func-returns-value]
    session.outcomes("main", 5, DAYS[0], lambda: scored.append(1) or None)  # type: ignore[arg-type,func-returns-value]
    assert len(scored) == 2
    session.release()
    session.outcomes("main", 20, DAYS[0], lambda: scored.append(1) or None)  # type: ignore[arg-type,func-returns-value]
    assert len(scored) == 3


def test_a_horizon_with_nothing_stored_in_its_span_fails_while_another_is_read() -> None:
    w = build_world()
    scope = _Scope("main", edge(), parse_selection(ACTIVE, "active"), "feature.x")
    stored = [Leg(DAYS[0], DAYS[1])]
    late = [Leg(DAYS[0], date(2027, 1, 4))]  # past every stored partition
    plans = [_Plan(scope, 2, [stored]), _Plan(scope, 5, [late])]
    out = _Measured({}, {}, {2: set(), 5: set()}, {}, {})
    failed: dict[int, Any] = {}
    closed = _read_closed(w.reader, plans, {DAYS[0]}, AS_OF, out, failed)
    assert set(failed) == {5} and closed[2] and not closed[5]
    with pytest.raises(Exception, match="no outcomes"):
        raise failed[5]
