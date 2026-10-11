"""``load_drafting_events``: the Describe-it events a viewer may read over a date range (ADR 0066):
a trader reads only their own rows, an admin all of them (the role is the registry's), newest
first within ``limit``, the sentence as stored (clipped at write), call ids split, and an older
partition without the optional columns reads as nulls."""

from datetime import UTC, date, datetime, timedelta

import pandas as pd

from algotrade.config.user import UserContext
from algotrade.data.feedback import DRAFTING_EVENTS
from algotrade.services.feedback.events import MAX_SENTENCE, row_of
from algotrade.services.feedback.recorder import FeedbackRecorder
from algotrade.services.read.context import StoreContext, open_stores
from algotrade.services.read.ops.feedback import load_drafting_events
from algotrade.services.read.users.viewer import Viewer
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.configs.files import MemoryConfigStore
from algotrade.storage.tables.feedback_writer import FeedbackWriter
from algotrade.storage.tables.readers import StoreReader
from algotrade.storage.tables.writers import StoreWriter
from tests.helpers.stored_frames import stamped

TODAY = date(2026, 10, 8)
NOON = datetime(2026, 10, 8, 16, tzinfo=UTC)
ADMIN = Viewer("abhi", "Abhi", "admin", ("trader", "admin"))
ALICE = Viewer("alice", "Alice", "trader", ("trader",))
BOB = Viewer("bob", "Bob", "trader", ("trader",))


def stores(rows: list[dict[str, object]], backend: MemoryBackend | None = None) -> StoreContext:
    backend = backend or MemoryBackend()
    recorder = FeedbackRecorder(FeedbackWriter(backend), clock=lambda: NOON)
    for row in rows:
        recorder.submit(row)
    recorder.flush()
    recorder.close()
    return open_stores(StoreReader(backend), MemoryConfigStore({}), UserContext("local"))


def event(user: str, name: str, minutes: int, **over: object) -> dict[str, object]:
    at = NOON + timedelta(minutes=minutes)
    return (
        row_of(name, f"s-{user}", user, "screen", "mine", at=at, sentence=f"{user} wants it") | over
    )


def ledger() -> list[dict[str, object]]:
    return [
        event("alice", "draft_requested", 0),
        event("alice", "draft_returned", 1, call_ids="c1,c2", payload='{"criteria":2}'),
        event("bob", "draft_requested", 2),
        event("alice", "draft_saved", 3),
    ]


def test_a_trader_reads_only_their_own_rows() -> None:
    ctx = stores(ledger())
    mine = load_drafting_events(ctx, ALICE, TODAY, today=TODAY)
    assert {e.user for e in mine} == {"alice"} and len(mine) == 3
    theirs = load_drafting_events(ctx, BOB, TODAY, today=TODAY)
    assert [e.user for e in theirs] == ["bob"]
    nobody = load_drafting_events(ctx, Viewer("carol", "C", "trader", ()), TODAY, today=TODAY)
    assert nobody == ()  # a user with no rows sees none, never another's


def test_an_admin_reads_everyones_rows_newest_first_within_the_limit() -> None:
    ctx = stores(ledger())
    everyone = load_drafting_events(ctx, ADMIN, TODAY, today=TODAY)
    assert [e.event for e in everyone] == [
        "draft_saved", "draft_requested", "draft_returned", "draft_requested",
    ]  # fmt: skip
    assert len(load_drafting_events(ctx, ADMIN, TODAY, limit=2, today=TODAY)) == 2
    assert load_drafting_events(ctx, ADMIN, TODAY, limit=0, today=TODAY) == ()


def test_the_role_is_the_viewers_not_a_claim_in_a_row() -> None:
    ctx = stores(ledger())
    admin_named_alice = Viewer("alice", "Alice", "trader", ("admin",))  # workspaces are no role
    assert {e.user for e in load_drafting_events(ctx, admin_named_alice, TODAY, today=TODAY)} == {
        "alice"
    }


def test_the_fields_come_back_split_and_clipped() -> None:
    clipped = row_of("draft_requested", "s", "alice", "screen", "m", at=NOON, sentence="y" * 5000)
    ctx = stores([*ledger(), clipped])
    got = load_drafting_events(ctx, ALICE, TODAY, today=TODAY)
    returned = next(e for e in got if e.event == "draft_returned")
    assert returned.call_ids == ("c1", "c2") and returned.payload == '{"criteria":2}'
    assert returned.draft_hash is None and returned.catalogue_version is None
    assert max(len(e.sentence or "") for e in got) == MAX_SENTENCE  # clipped when written


def test_the_range_and_an_empty_store() -> None:
    ctx = stores(ledger())
    assert load_drafting_events(ctx, ADMIN, TODAY + timedelta(days=1), today=TODAY) == ()
    empty = open_stores(StoreReader(MemoryBackend()), MemoryConfigStore({}), UserContext("local"))
    assert load_drafting_events(empty, ADMIN, TODAY, today=TODAY) == ()


def test_an_older_partition_without_the_optional_columns_reads_as_nulls() -> None:
    backend = MemoryBackend()
    old = [{"event_id": "e1", "draft_session_id": "s1", "ts": pd.Timestamp(NOON), "user": "alice",
            "doc_kind": "screen", "doc_id": "mine", "event": "draft_requested"}]  # fmt: skip
    StoreWriter(backend).write_table(DRAFTING_EVENTS, TODAY, "r0", stamped(old, TODAY, "r0"))
    ctx = open_stores(StoreReader(backend), MemoryConfigStore({}), UserContext("local"))
    (only,) = load_drafting_events(ctx, ALICE, TODAY, today=TODAY)
    assert only.sentence is None and only.call_ids == () and only.payload is None
