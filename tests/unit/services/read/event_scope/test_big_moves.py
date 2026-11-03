"""``attributed_moves``: of the 20 largest moves of the last year, how many have an attribution
known by the session (any source), None for a name with under a year of bars."""

from datetime import UTC, date, datetime, time

import numpy as np
import pandas as pd

from algotrade.core.time.calendar import sessions_ending
from algotrade.data import StoreReader
from algotrade.services.read.event_scope.big_moves import attributed_moves
from tests.helpers.rollup_store import store, write_bars
from tests.helpers.stored_frames import stamped

SESSION = date(2026, 10, 1)
AAA, BBB = "EQ:AAA", "EQ:BBB"
N = 270


def closes(jumps: dict[int, float]) -> list[float]:
    """A quiet series (+/-0.1% alternating) with the given log jumps at the given indexes."""
    out, price = [], 100.0
    for i in range(N):
        price *= np.exp(jumps.get(i, 0.001 if i % 2 else -0.001))
        out.append(price)
    return out


def attribution(instrument_id: str, day: date, known: date) -> dict[str, object]:
    return {
        "instrument_id": instrument_id, "ts": pd.Timestamp(day, tz="UTC"), "known_from": known,
        "cause_class": "results", "cause_text": "t", "confidence": 0.8, "evidence": "e",
        "evidence_ref": None, "model": None,
    }  # fmt: skip


def world(attributed: list[int], known: date = SESSION) -> StoreReader:
    writer, reader = store()
    jumps = {
        20 + 5 * k: 0.04 + 0.01 * k for k in range(25)
    }  # 25 distinct big moves, k = 24 largest
    write_bars(writer, {AAA: closes(jumps), BBB: closes({})[:100]}, SESSION)
    days = sessions_ending(SESSION, N)
    rows = [attribution(AAA, days[20 + 5 * k], known) for k in attributed]
    if rows:
        stored = datetime.combine(known, time(23), UTC)
        writer.write_table(
            "events/attribution", known, "attr", stamped(rows, known, "attr", stored)
        )
    return reader


def test_the_share_of_the_twenty_largest_moves_that_are_attributed() -> None:
    # moves k = 5..24 are the 20 largest; attribute 4 of them and 2 smaller ones (k = 0, 1)
    found = attributed_moves(world([24, 23, 10, 5, 0, 1]), SESSION, [AAA])
    assert found[AAA].big == 20 and found[AAA].attributed == 4 and found[AAA].share == 0.2


def test_nothing_attributed_is_zero_not_unknown() -> None:
    found = attributed_moves(world([]), SESSION, [AAA])
    assert (found[AAA].big, found[AAA].attributed, found[AAA].share) == (20, 0, 0.0)


def test_an_attribution_known_after_the_session_does_not_count() -> None:
    late = attributed_moves(world([24, 23], known=date(2026, 10, 5)), SESSION, [AAA])
    assert late[AAA].attributed == 0


def test_a_name_with_under_a_year_of_bars_has_no_share() -> None:
    found = attributed_moves(world([24]), SESSION, [AAA, BBB])
    assert BBB not in found and AAA in found


def test_nothing_asked_or_nothing_stored() -> None:
    assert attributed_moves(world([]), SESSION, []) == {}
    _, reader = store()
    assert attributed_moves(reader, SESSION, [AAA]) == {}
