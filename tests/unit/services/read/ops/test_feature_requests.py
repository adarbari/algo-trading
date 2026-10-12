"""``load_my_requests`` and ``load_ranked_requests`` (ADR 0066 amendment): a trader reads only their
own history, never a count or trace of another user, and gets an authorization error for the ranked
list; an admin reads the ranked list across users, and their own "my requests" is theirs only."""

from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

import pytest

from algotrade.config.user import UserContext
from algotrade.core.model.errors import PermissionDeniedError
from algotrade.services.feedback.request_recorder import FeatureRequestRecorder
from algotrade.services.feedback.requests import request_row
from algotrade.services.read.context import StoreContext, open_stores
from algotrade.services.read.ops.feature_requests import load_my_requests, load_ranked_requests
from algotrade.services.read.users.viewer import Viewer
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.configs.files import MemoryConfigStore
from algotrade.storage.tables.feedback_writer import FeedbackWriter
from algotrade.storage.tables.readers import StoreReader

TODAY = date(2026, 10, 8)
NOON = datetime(2026, 10, 8, 16, tzinfo=UTC)
ADMIN = Viewer("abhi", "Abhi", "admin", ("trader", "admin"))
ALICE = Viewer("alice", "Alice", "trader", ("trader",))
BOB = Viewer("bob", "Bob", "trader", ("trader",))
BACKLOG = {
    ("site", "settings", "feature_backlog"): {
        "item": [
            {"key": "fcf_yield", "description": "FCF over price", "feasibility": "NEEDS_SOURCE",
             "aliases": ["fcf"]},
        ]
    }
}  # fmt: skip


def item(key: str | None, slug: str | None = None, feasibility: str = "UNCLEAR") -> SimpleNamespace:
    return SimpleNamespace(
        key=key, new_key_slug=slug, span="my span", closest=(), feasibility=feasibility
    )


def ask(user: str, ref: str, days_ago: int = 0, feasibility: str = "UNCLEAR") -> dict[str, object]:
    known = ref in ("fcf_yield",)
    made = request_row(
        user,
        item(ref if known else None, None if known else ref, feasibility),
        "my span",
        at=NOON - timedelta(days=days_ago),
    )
    assert made is not None
    return made


def stores(rows: list[dict[str, object]], documents: bool = True) -> StoreContext:
    backend = MemoryBackend()
    recorder = FeatureRequestRecorder(FeedbackWriter(backend), clock=lambda: NOON)
    for r in rows:
        recorder.submit(r)
    recorder.flush()
    recorder.close()
    configs = MemoryConfigStore(BACKLOG if documents else {})
    return open_stores(StoreReader(backend), configs, UserContext("local"))


def ledger() -> list[dict[str, object]]:
    return [
        ask("alice", "fcf_yield", 20),
        ask("alice", "fcf_yield", 2),
        ask("alice", "gamma_squeeze", 1),
        ask("bob", "fcf_yield", 0),
        ask("bob", "bob_secret_idea", 0),
    ]


def test_a_trader_reads_only_their_own_history() -> None:
    ctx = stores(ledger())
    mine = load_my_requests(ctx, ALICE, TODAY)
    assert [(r.ref, r.times_asked) for r in mine] == [("gamma_squeeze", 1), ("fcf_yield", 2)]
    fcf = {r.ref: r for r in mine}["fcf_yield"]
    assert (fcf.first_asked, fcf.last_asked) == (date(2026, 9, 18), date(2026, 10, 6))
    assert fcf.status == "OPEN" and not fcf.unmapped and fcf.description == "FCF over price"
    assert {r.ref for r in load_my_requests(ctx, BOB, TODAY)} == {"fcf_yield", "bob_secret_idea"}
    # nothing of bob's reaches alice: not a row, not a count, not the unmapped slug
    assert "bob_secret_idea" not in {r.ref for r in mine}
    assert not hasattr(mine[0], "users") and not hasattr(mine[0], "score")


def test_my_history_carries_the_latest_span_and_feasibility() -> None:
    ctx = stores(
        [ask("alice", "gamma_squeeze", 4, "NEEDS_SOURCE"), ask("alice", "gamma_squeeze", 1)]
    )
    (mine,) = load_my_requests(ctx, ALICE, TODAY)
    assert (mine.span, mine.feasibility) == ("my span", "UNCLEAR")  # the newest ask's
    backlog = {
        r.ref: r for r in load_my_requests(stores([ask("alice", "fcf_yield")]), ALICE, TODAY)
    }
    assert backlog["fcf_yield"].feasibility == "NEEDS_SOURCE"  # the backlog item's


def test_an_admin_own_history_is_their_own_too() -> None:
    ctx = stores([*ledger(), ask("abhi", "treasury_level", 3)])
    assert [r.ref for r in load_my_requests(ctx, ADMIN, TODAY)] == ["treasury_level"]
    assert load_my_requests(ctx, Viewer("nobody", "N", "trader", ("trader",)), TODAY) == ()


def test_my_history_reads_an_alias_under_its_key_and_unmapped_slugs_say_so() -> None:
    ctx = stores([ask("alice", "fcf", 5), ask("alice", "fcf_yield", 1), ask("alice", "new_one")])
    by = {r.ref: r for r in load_my_requests(ctx, ALICE, TODAY)}
    assert by["fcf_yield"].times_asked == 2 and by["new_one"].unmapped
    assert by["new_one"].status == "UNMAPPED"


def test_a_trader_cannot_read_the_ranked_list() -> None:
    ctx = stores(ledger())
    for viewer in (ALICE, BOB):
        with pytest.raises(PermissionDeniedError):
            load_ranked_requests(ctx, viewer, TODAY)
    with pytest.raises(PermissionDeniedError):  # even a role the registry did not name
        load_ranked_requests(ctx, Viewer("x", "X", "guest", ()), TODAY)


def test_an_admin_reads_the_ranked_list_across_users() -> None:
    ctx = stores(ledger())
    ranked = load_ranked_requests(ctx, ADMIN, TODAY)
    assert ranked[0].ref == "fcf_yield" and ranked[0].users == 2 and ranked[0].status == "OPEN"
    slugs = {r.ref: r for r in ranked}
    assert slugs["gamma_squeeze"].unmapped and slugs["bob_secret_idea"].unmapped
    assert [r.score for r in ranked] == sorted((r.score for r in ranked), reverse=True)


def test_requests_outside_the_window_are_not_read_and_nothing_stored_reads_empty() -> None:
    old = stores([ask("alice", "fcf_yield", 400)])
    assert load_my_requests(old, ALICE, TODAY) == ()
    assert load_ranked_requests(old, ADMIN, TODAY) == ()
    empty = stores([], documents=False)
    assert load_my_requests(empty, ALICE, TODAY) == ()
    assert load_ranked_requests(empty, ADMIN, TODAY) == ()


def test_an_older_partition_without_optional_columns_reads() -> None:
    # the reads need only user, ref, feasibility and the day: a partition lacking the rest is fine
    ctx = stores([ask("alice", "fcf_yield", 1) | {"feasibility": None}])
    assert load_ranked_requests(ctx, ADMIN, TODAY)[0].feasibility == "NEEDS_SOURCE"
