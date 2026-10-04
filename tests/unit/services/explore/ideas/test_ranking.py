from datetime import UTC, date, datetime, timedelta

import pytest

from algotrade.config.user import UserContext
from algotrade.services.explore.ideas.ranking import ideas_for, top_ideas
from algotrade.services.explore.store import NotFoundError, store_over
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.configs.files import MemoryConfigStore
from algotrade.storage.tables.readers import StoreReader
from algotrade.storage.tables.writers import StoreWriter
from tests.helpers.stored_frames import stamped, write_reference

D1, D2 = date(2026, 9, 30), date(2026, 10, 1)
T = datetime(2026, 10, 1, 3, tzinfo=UTC)


class Stored(StoreWriter):
    def __init__(self) -> None:
        self.backend = MemoryBackend()
        super().__init__(self.backend)


def _write(
    writer: Stored,
    day: date,
    run: str,
    config: str,
    rows: list[tuple],
    user: str = "site",
    knowledge: datetime = T,
) -> None:
    frame = [
        {"instrument_id": f"EQ:{s}", "user_id": user, "config_id": config, "config_version": 1,
         "config_hash": "h", "decision": d, "score": sc, "rank": 1, "tie_break": tb, "tier": "",
         "class": "", "flags": "", "reasons": "", "failed": "", "near_missed": "", "missing": ""}
        for s, d, sc, tb in rows
    ]  # fmt: skip
    writer.write_result("rule_screen", day, run, stamped(frame, day, run, knowledge))


@pytest.fixture
def writer() -> Stored:
    w = Stored()
    write_reference(w, D2, {s: f"EQ:{s}" for s in ("AAA", "BBB", "CCC")})
    return w


def test_priority_then_score_then_tie_break_then_id(writer: Stored) -> None:
    _write(
        writer, D2, "r1", "a", [("AAA", "QUALIFIED", 50.0, None), ("BBB", "QUALIFIED", 90.0, None)]
    )
    _write(writer, D2, "r2", "b", [("CCC", "QUALIFIED", 10.0, None), ("BBB", "WATCH", 70.0, 2.0)])
    reader = StoreReader(writer.backend) if hasattr(writer, "_backend") else None
    assert reader is not None
    by_b = top_ideas(reader, None, "local", ["b", "a"], 10)
    assert [i.instrument_id for i in by_b.items] == ["EQ:BBB", "EQ:CCC", "EQ:AAA"]
    assert [p.config_id for p in by_b.items[0].picks] == ["b", "a"]
    by_a = top_ideas(reader, None, "local", ["a"], 10)
    assert [i.instrument_id for i in by_a.items] == ["EQ:BBB", "EQ:AAA", "EQ:CCC"]
    assert top_ideas(reader, None, "local", ["a"], 1).total == 3


def test_latest_run_per_config_and_session_bound(writer: Stored) -> None:
    _write(writer, D1, "old", "a", [("AAA", "QUALIFIED", 80.0, None)])
    _write(writer, D2, "run1", "a", [("BBB", "QUALIFIED", 60.0, None)])
    _write(
        writer,
        D2,
        "run2",
        "a",
        [("CCC", "QUALIFIED", 70.0, None)],
        knowledge=T + timedelta(hours=1),
    )
    reader = StoreReader(writer.backend)
    latest = top_ideas(reader, None, "local", [], 10)
    assert latest.session == D2
    assert [i.instrument_id for i in latest.items] == ["EQ:CCC"]  # run2 only
    earlier = top_ideas(reader, D1, "local", [], 10)
    assert [i.instrument_id for i in earlier.items] == ["EQ:AAA"]
    with pytest.raises(NotFoundError):
        top_ideas(reader, date(2020, 1, 1), "local", [], 10)


def test_rejected_and_skipped_are_not_picks_and_users_screen_wins(writer: Stored) -> None:
    _write(writer, D2, "s", "a", [("AAA", "QUALIFIED", 99.0, None)], user="site")
    _write(writer, D2, "u", "a", [("BBB", "QUALIFIED", 5.0, None), ("AAA", "REJECT", 0.0, None),
                                  ("CCC", "SKIPPED", None, None)], user="me")  # fmt: skip
    reader = StoreReader(writer.backend)
    mine = top_ideas(reader, None, "me", [], 10)
    assert [i.instrument_id for i in mine.items] == ["EQ:BBB"]
    assert [i.instrument_id for i in top_ideas(reader, None, "you", [], 10).items] == ["EQ:AAA"]


def test_priority_is_read_from_the_users_preferences(writer: Stored) -> None:
    _write(writer, D2, "r1", "a", [("AAA", "QUALIFIED", 50.0, None)])
    _write(writer, D2, "r2", "b", [("BBB", "QUALIFIED", 10.0, None)])
    docs = {("me", "preferences", "preferences"): {"ideas": {"priority": ["b", "a"]}}}
    store = store_over(writer.backend, MemoryConfigStore(docs), UserContext("local"))
    ideas = ideas_for(store, None, "me", 10)
    assert ideas.priority == ["b", "a"]
    assert [i.instrument_id for i in ideas.items] == ["EQ:BBB", "EQ:AAA"]
    assert ideas_for(store, None, None, 10).priority == []
