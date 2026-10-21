"""``restamp-known-from``: stored FINRA rows get the schedule's ``known_from`` with no refetch
(``min(stored, schedule)``), a flagged or restated row keeps its stamp, values never change, a
dry run writes nothing and a second run changes nothing."""

from datetime import UTC, date, datetime

import pandas as pd

from algotrade.data import StoreReader
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.tables.writers import StoreWriter
from algotrade_ingestion.tasks.framework.registry import run_task
from algotrade_ingestion.tasks.shorting import restamp, schedule, short_interest, short_volume
from tests.helpers.ingest_fakes import task_ctx

SETTLE, TRADE = date(2026, 9, 30), date(2026, 10, 15)
LATE, EARLY = date(2026, 10, 20), date(2026, 10, 1)
SCHED = schedule.short_interest_known_from(SETTLE)
T0 = datetime(2026, 10, 19, 12, tzinfo=UTC)
T1 = datetime(2026, 10, 20, 12, tzinfo=UTC)


def _interest(sym: str, known: date, shorts: int, flag: str | None = None) -> dict:
    return {
        "instrument_id": f"EQ:{sym}", "ts": pd.Timestamp(SETTLE, tz="UTC"),
        "short_position": shorts, "previous_short_position": 1, "change_shares": 1,
        "change_percent": 1.0, "average_daily_volume": 10, "days_to_cover": 1.0,
        "market_class": "NYSE", "revision_flag": flag, "split_flag": None,
        "published": schedule.publication_date(SETTLE), "known_from": known,
        "session_date": SETTLE,
    }  # fmt: skip


def _put(writer: StoreWriter, table: str, day: date, rows: list[dict], run: str, at: datetime):
    frame = pd.DataFrame(rows).assign(knowledge_ts=pd.Timestamp(at), source="finra", run_id=run)
    for column in ("revision_flag", "split_flag", "market_class"):
        if column in frame:
            frame[column] = frame[column].astype("string")
    writer.write_table(table, day, run, frame, pending=True)
    writer.commit_run(run, at)


def _stamps(writer: StoreWriter, table: str, day: date) -> dict[str, date]:
    frame = StoreReader(writer._backend).table(table, day)
    return dict(zip(frame["instrument_id"], frame["known_from"], strict=True))


def _run(writer: StoreWriter, dry_run: bool = False):
    return run_task("restamp-known-from", task_ctx(writer, clock=lambda: T1), {
        "session": date(2026, 10, 20), "dry_run": dry_run,
    })  # fmt: skip


def test_restamp_lowers_unflagged_and_keeps_flagged_earlier_and_restated() -> None:
    writer = StoreWriter(MemoryBackend())
    table = short_interest.TABLE
    first = [
        _interest("LATE", LATE, 5),
        _interest("FLAG", LATE, 5, "R"),
        _interest("EARLY", EARLY, 5),
        _interest("REST", LATE, 5),
    ]
    _put(writer, table, SETTLE, first, "run-a", T0)
    # REST was restated by a later run (value 6): its late stamp is deliberate
    _put(writer, table, SETTLE, [_interest("REST", LATE, 6)], "run-b", T1)
    before = StoreReader(writer._backend).table(table, SETTLE)
    run_ = _run(writer)
    after = StoreReader(writer._backend).table(table, SETTLE)
    got = _stamps(writer, table, SETTLE)
    assert got == {"EQ:LATE": SCHED, "EQ:FLAG": LATE, "EQ:EARLY": EARLY, "EQ:REST": LATE}
    cols = [c for c in before.columns if c not in ("known_from", "knowledge_ts", "run_id")]
    key = ["instrument_id"]
    same = before.sort_values(key).reset_index(drop=True)[cols]
    assert same.equals(after.sort_values(key).reset_index(drop=True)[cols])
    assert run_.stats["restamped"][table] == 1


def test_dry_run_writes_nothing_and_a_second_run_changes_nothing() -> None:
    writer = StoreWriter(MemoryBackend())
    _put(writer, short_interest.TABLE, SETTLE, [_interest("A", LATE, 5)], "run-a", T0)
    run_ = _run(writer, dry_run=True)
    assert run_.stats["restamped"][short_interest.TABLE] == 1
    assert _stamps(writer, short_interest.TABLE, SETTLE) == {"EQ:A": LATE}
    _run(writer)
    assert _stamps(writer, short_interest.TABLE, SETTLE) == {"EQ:A": SCHED}
    assert _run(writer).stats["restamped"][short_interest.TABLE] == 0


def test_short_volume_follows_the_session_after_the_trade_date() -> None:
    writer = StoreWriter(MemoryBackend())
    row = {
        "instrument_id": "EQ:A", "ts": pd.Timestamp(TRADE, tz="UTC"), "short_volume": 1,
        "short_exempt_volume": 0, "total_volume": 2, "facilities": 1, "known_from": LATE,
        "session_date": TRADE,
    }  # fmt: skip
    _put(writer, short_volume.TABLE, TRADE, [row], "run-a", T0)
    _run(writer)
    assert _stamps(writer, short_volume.TABLE, TRADE) == {
        "EQ:A": schedule.short_volume_known_from(TRADE)
    }


def test_restamped_never_raises_a_stamp() -> None:
    frame = pd.DataFrame([_interest("A", EARLY, 5)])
    out = restamp.restamped(frame, schedule.short_interest_known_from, [])
    assert out["known_from"].tolist() == [EARLY]
