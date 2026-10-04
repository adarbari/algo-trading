from datetime import UTC, date, datetime, timedelta

import pandas as pd
import pytest

from algotrade.config.user import UserContext
from algotrade.features.rollups import earnings
from algotrade.services.explore.ideas.ranking import ideas_for, top_ideas
from algotrade.services.explore.store import store_over
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
    before = top_ideas(reader, date(2020, 1, 1), "local", ["a"], 10)  # nothing stored by then
    assert (before.session, before.items, before.screeners, before.total) == (None, [], [], 0)
    assert before.priority == ["a"]


def test_an_empty_store_is_no_ideas_not_an_error(writer: Stored) -> None:
    empty = top_ideas(StoreReader(writer.backend), None, "local", [], 10)
    assert (empty.session, empty.items, empty.total) == (None, [], 0)


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


def _chain(writer: Stored, session: date, expiries: dict[str, list[date]]) -> None:
    ts = pd.Timestamp(T)
    rows = [
        {"instrument_id": f"OPT:{u}{n}", "underlying_id": f"EQ:{u}", "ts": ts, "expiry": e,
         "right": "P", "strike": 100.0, "bid": 1.0, "ask": 1.1, "volume": 1.0,
         "open_interest": 1.0, "iv": 0.3, "delta": -0.3}
        for u, days in expiries.items() for n, e in enumerate(days)
    ]  # fmt: skip
    writer.write_table("chains/option_quotes", session, "ch", stamped(rows, session, "ch"))


def _earnings(writer: Stored, session: date, when: dict[str, date]) -> None:
    rows = [
        {"instrument_id": f"EQ:{s}", "next_earnings_date": d, "days_to_earnings": 3}
        for s, d in when.items()
    ]
    writer.write_table(earnings.GROUP.table, session, "er", stamped(rows, session, "er"))


def test_closest_expiry_dte_is_the_nearest_on_or_after_the_session(writer: Stored) -> None:
    _write(writer, D2, "r", "a", [("AAA", "QUALIFIED", 9.0, None), ("BBB", "QUALIFIED", 8.0, None)])
    _chain(
        writer, D2, {"AAA": [date(2026, 9, 25), D2, date(2026, 10, 9)], "BBB": [date(2026, 10, 16)]}
    )
    _earnings(writer, D2, {"AAA": date(2026, 10, 9), "BBB": date(2026, 10, 20)})
    got = {i.symbol: i for i in top_ideas(StoreReader(writer.backend), None, "local", [], 10).items}
    assert (got["AAA"].closest_expiry_dte, got["AAA"].earnings_before_expiry) == (0, False)
    assert (got["BBB"].closest_expiry_dte, got["BBB"].earnings_before_expiry) == (15, False)
    _earnings(writer, D2, {"AAA": D2, "BBB": date(2026, 10, 16)})
    got = {i.symbol: i for i in top_ideas(StoreReader(writer.backend), None, "local", [], 10).items}
    assert got["AAA"].earnings_before_expiry is True and got["BBB"].earnings_before_expiry is True


def test_no_chain_or_no_earnings_gives_null(writer: Stored) -> None:
    _write(writer, D2, "r", "a", [("AAA", "QUALIFIED", 9.0, None), ("BBB", "QUALIFIED", 8.0, None)])
    _chain(writer, D2, {"AAA": [date(2026, 10, 9)]})
    got = {i.symbol: i for i in top_ideas(StoreReader(writer.backend), None, "local", [], 10).items}
    assert (got["AAA"].closest_expiry_dte, got["AAA"].earnings_before_expiry) == (8, None)
    assert (got["BBB"].closest_expiry_dte, got["BBB"].earnings_before_expiry) == (None, None)


def test_a_later_chain_is_not_visible(writer: Stored) -> None:
    _write(writer, D2, "r", "a", [("AAA", "QUALIFIED", 9.0, None)])
    _chain(writer, date(2026, 10, 2), {"AAA": [date(2026, 10, 9)]})
    only = top_ideas(StoreReader(writer.backend), None, "local", [], 10).items[0]
    assert only.closest_expiry_dte is None


def _values(writer: Stored, config: str, rows: list[tuple]) -> None:
    frame = [
        {"instrument_id": f"EQ:{s}", "user_id": "site", "config_id": config, "criterion_id": c,
         "field": f"feature.{c}", "mode": "column" if o == "INFO" else "hard", "value_num": v,
         "value_str": None, "outcome": o, "distance": None, "normalised": None, "penalty": None}
        for s, c, o, v in rows
    ]  # fmt: skip
    writer.write_result("rule_screen_values", D2, "r", stamped(frame, D2, "r"))


def test_picks_carry_columns_criterion_values_and_flags(writer: Stored) -> None:
    _write(writer, D2, "r", "a", [("AAA", "QUALIFIED", 9.0, None)])
    _values(writer, "a", [("AAA", "iv30", "INFO", 0.62), ("AAA", "iv30", "PASS", 0.62),
                          ("AAA", "adv", "NEAR", 4.5e7)])  # fmt: skip
    pick = top_ideas(StoreReader(writer.backend), None, "local", [], 10).items[0].picks[0]
    assert pick.columns == {"iv30": 0.62}
    assert pick.criterion_values == {"iv30": 0.62, "adv": 4.5e7}
    assert pick.flags == []


def test_screeners_list_names_versions_and_priority(writer: Stored) -> None:
    _write(writer, D2, "r1", "a", [("AAA", "QUALIFIED", 50.0, None)])
    _write(writer, D2, "r2", "b", [("BBB", "QUALIFIED", 10.0, None)])
    docs = {
        ("site", "screeners", "a"): {"name": "Alpha scan"},
        ("me", "preferences", "preferences"): {"ideas": {"priority": ["gone", "b"]}},
    }
    store = store_over(writer.backend, MemoryConfigStore(docs), UserContext("local"))
    got = ideas_for(store, None, "me", 10).screeners
    assert [(s.config_id, s.name, s.user, s.version) for s in got] == [
        ("gone", "gone", None, None),
        ("b", "b", "site", 1),
        ("a", "Alpha scan", "site", 1),
    ]
