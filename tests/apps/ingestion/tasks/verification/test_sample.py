"""The verification sample: core names first, then the session's event names, then rotating
names chosen by a hash of the session (deterministic, varying across sessions)."""

from datetime import date

import pandas as pd

from algotrade.data.resolver import SymbolResolver
from algotrade_ingestion.tasks.verification import sample
from tests.helpers.rollup_store import store, write_dividends, write_split
from tests.helpers.stored_frames import stamped

D = date(2026, 10, 2)
SYMBOLS = ["AAPL", "SPY", "KO", "BRK.B", "KIM$L", *(f"N{a}{b}" for a in "ABCDE" for b in "XYZ")]
RESOLVER = SymbolResolver.from_reference(
    pd.DataFrame({"instrument_id": [f"EQ:{s}" for s in SYMBOLS], "symbol": SYMBOLS}), D
)
ALL = [f"EQ:{s}" for s in SYMBOLS]


def test_core_then_events_then_rotating_without_repeats() -> None:
    picks = sample.choose(RESOLVER, D, ["AAPL", "SPY"], 5, ["EQ:KO", "EQ:AAPL", "EQ:KIM$L"], ALL)
    assert [(p.symbol, p.why) for p in picks[:3]] == [
        ("AAPL", "core"),
        ("SPY", "core"),
        ("KO", "event"),
    ]  # KIM$L (a preferred) has no IB stock contract under our spelling
    rotating = [p for p in picks if p.why == "rotating"]
    assert len(rotating) == 5 and len({p.instrument_id for p in picks}) == len(picks)
    assert all(p.symbol not in ("AAPL", "SPY", "KO", "KIM$L") for p in rotating)


def test_rotation_is_deterministic_per_session_and_moves_across_sessions() -> None:
    def names(day: date) -> list[str]:
        return [p.symbol for p in sample.choose(RESOLVER, day, [], 5, [], ALL)]

    assert names(D) == names(D)
    assert names(D) != names(date(2026, 10, 5))


def test_requested_symbols() -> None:
    picks = sample.requested(RESOLVER, ["aapl", "NEW"])
    assert [(p.symbol, p.instrument_id, p.why) for p in picks] == [
        ("AAPL", "EQ:AAPL", "requested"),
        ("NEW", "EQ:NEW", "requested"),
    ]


def test_event_ids_are_the_sessions_corporate_actions_and_changes() -> None:
    writer, reader = store()
    write_split(writer, "EQ:SPLIT", D, 2.0, D)
    write_split(writer, "EQ:OLD", date(2026, 9, 1), 2.0, date(2026, 9, 1))  # not this session
    write_dividends(writer, [("EQ:DIV", D, 0.5, "recurring")])
    changes = [
        {"instrument_id": "EQ:REN", "symbol": "REN", "change": "renamed", "old": "a", "new": "b",
         "ts": pd.Timestamp(D, tz="UTC")},
        {"instrument_id": "EQ:ADD", "symbol": "ADD", "change": "added", "old": None, "new": "x",
         "ts": pd.Timestamp(D, tz="UTC")},
    ]  # fmt: skip
    writer.write_table("events/reference_change", D, "rc", stamped(changes, D, "rc"))
    assert sample.event_ids(reader, D) == ["EQ:DIV", "EQ:REN", "EQ:SPLIT"]
