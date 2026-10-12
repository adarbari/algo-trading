"""``load_accepted_formulas`` (ADR 0066 note 2026-10-11): an admin reads the formulas traders
accepted grouped by fingerprint, counts only; a trader is refused before anything is read; a row
without a fingerprint (older, nulled by erase / retain) is skipped; the duplicate of a site feature
and the exact backlog match are flagged."""

import dataclasses
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from typing import Any, cast

import pytest

from algotrade.config.site.features.definitions import feature_definitions
from algotrade.core.model.errors import PermissionDeniedError
from algotrade.features.expressions.fingerprint import fingerprint
from algotrade.services.feedback.events import row_of
from algotrade.services.feedback.formulas.payload import accepted_payload
from algotrade.services.feedback.recorder import FeedbackRecorder
from algotrade.services.read.context import Stores
from algotrade.services.read.formulas.accepted import (
    AcceptedFormula,
    load_accepted_formula_list,
    load_accepted_formulas,
)
from algotrade.services.read.users.viewer import Viewer
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.configs.files import MemoryConfigStore
from algotrade.storage.tables.feedback_writer import FeedbackWriter
from algotrade.storage.tables.readers import StoreReader

TODAY = date(2026, 10, 8)
NOON = datetime(2026, 10, 8, 16, tzinfo=UTC)
SINCE = date(2026, 1, 1)
ADMIN = Viewer("abhi", "Abhi", "admin", ("trader", "admin"))
ALICE = Viewer("alice", "Alice", "trader", ("trader",))


def section(expr: str, unit: str = "pct_points") -> dict[str, str]:
    return {
        "expr": expr, "dtype": "float", "unit": unit, "description": "d", "null_meaning": "n",
    }  # fmt: skip


SITE = {"vol": {"hv_pct": section("price_stats.hv20 * 100")}}
BACKLOG = {
    ("site", "settings", "feature_backlog"): {
        "item": [
            {"key": "near_high", "description": "close to the high", "aliases": ["nh"],
             "feasibility": "ROLLUP_FROM_STORED"},
            {"key": "hv_percent", "description": "hv in percent", "status": "PROMOTED",
             "promoted_to": "hv_pct", "feasibility": "ROLLUP_FROM_STORED"},
        ]
    },
    ("site", "features", "vol"): SITE["vol"],
}  # fmt: skip


def accepted(
    user: str, feature: str, expr: str, days_ago: int = 0, event_id: str | None = None
) -> dict[str, Any]:
    docs = {"builder": {feature: section(expr)}}
    payload = accepted_payload("draft_" + feature, user, feature, docs)
    row = row_of(
        "formula_accepted", "s-" + user, user, "screen", "s",
        at=NOON - timedelta(days=days_ago), payload=payload,
    )  # fmt: skip
    if event_id:
        row["event_id"] = event_id
    return row


def stores(rows: list[dict[str, Any]]) -> Stores:
    backend = MemoryBackend()
    recorder = FeedbackRecorder(FeedbackWriter(backend), clock=lambda: NOON)
    for r in rows:
        recorder.submit(r)
    recorder.flush()
    recorder.close()
    # the loader reads only the reader and the configs: not the whole catalogue (a site document
    # of its own would replace the real one the catalogue needs)
    ctx = SimpleNamespace(reader=StoreReader(backend), configs=MemoryConfigStore(BACKLOG))
    return cast(Stores, ctx)


def test_a_trader_is_refused_before_anything_is_read() -> None:
    ctx = stores([accepted("alice", "near_high", "price_stats.close / price_stats.high")])
    with pytest.raises(PermissionDeniedError):
        load_accepted_formulas(ctx, ALICE, SINCE, TODAY)
    with pytest.raises(PermissionDeniedError):
        load_accepted_formula_list(ctx, ALICE, TODAY)
    with pytest.raises(PermissionDeniedError):
        load_accepted_formulas(ctx, Viewer("x", "X", "", ()), SINCE, TODAY)


def test_formulas_group_by_fingerprint_with_distinct_users_and_events() -> None:
    ctx = stores(
        [
            accepted("alice", "x", "a.b / a.c", 5),
            accepted("bob", "y", "a.b / a.c", 2),  # the same formula, another name
            accepted("alice", "x2", "a.b / a.c", 0, event_id="e-dup"),
            accepted("alice", "x2", "a.b / a.c", 0, event_id="e-dup"),  # same event twice
            accepted("carol", "z", "a.b - a.c", 1),
        ]
    )
    first, second = load_accepted_formulas(ctx, ADMIN, SINCE, TODAY)
    assert (first.users, first.accepted_count) == (2, 3)  # alice, bob; the dup event is one
    assert (first.first_accepted, first.last_accepted) == (date(2026, 10, 3), date(2026, 10, 8))
    assert first.expression == "a.b / a.c" and first.unit == "pct_points"
    assert (second.users, second.accepted_count, second.expression) == (1, 1, "a.b - a.c")
    assert first.fingerprint != second.fingerprint and first.canonical == "(/ a.b a.c)"
    assert not [
        f.name
        for f in dataclasses.fields(AcceptedFormula)
        if "user" in f.name.lower() and f.name != "users"
    ]


def test_the_order_is_users_then_count_then_latest() -> None:
    ctx = stores(
        [
            accepted("alice", "a", "a.x + 1", 9),
            accepted("alice", "a", "a.x + 1", 8, event_id="e2"),  # 1 user, 2 events
            accepted("bob", "b", "b.x + 1", 0),  # 1 user, 1 event, newest
            accepted("bob", "c", "c.x + 1", 3),
            accepted("carol", "c", "c.x + 1", 4),  # 2 users: first
        ]
    )
    rows = load_accepted_formulas(ctx, ADMIN, SINCE, TODAY)
    assert [r.expression for r in rows] == ["c.x + 1", "a.x + 1", "b.x + 1"]


def test_a_row_without_a_fingerprint_is_skipped_and_the_window_is_honoured() -> None:
    nulled = accepted("alice", "a", "a.x + 1")
    nulled["payload"] = None  # erased or retained
    old_style = row_of(
        "formula_accepted", "s", "bob", "screen", "s", at=NOON,
        payload={"subject": "draft_a", "picked": None},
    )  # fmt: skip
    ctx = stores([nulled, old_style, accepted("carol", "c", "c.x + 1", 200)])
    assert load_accepted_formulas(ctx, ADMIN, SINCE, TODAY)[0].users == 1
    assert len(load_accepted_formulas(ctx, ADMIN, SINCE, TODAY)) == 1
    assert load_accepted_formulas(ctx, ADMIN, TODAY - timedelta(days=30), TODAY) == ()
    assert load_accepted_formulas(stores([]), ADMIN, SINCE, TODAY) == ()
    listed = load_accepted_formula_list(ctx, ADMIN, TODAY, days=365)
    assert (listed.today, listed.days, len(listed.rows)) == (TODAY, 365, 1)


def test_a_formula_equal_to_a_site_feature_names_it() -> None:
    ctx = stores([accepted("alice", "my_hv", "100 * price_stats.hv20")])  # written differently
    (row,) = load_accepted_formulas(ctx, ADMIN, SINCE, TODAY)
    (site,) = feature_definitions(SITE)
    assert row.fingerprint == fingerprint(site).hash
    assert row.duplicate_of == "hv_pct"
    assert row.backlog_key == "hv_percent"  # the backlog item promoted to that feature
    other = stores([accepted("alice", "my_x", "a.b / a.c")])
    assert load_accepted_formulas(other, ADMIN, SINCE, TODAY)[0].duplicate_of == ""


def test_the_backlog_match_is_exact_on_the_name_minus_draft_or_an_alias() -> None:
    ctx = stores(
        [
            accepted("alice", "near_high", "a.b / a.c"),  # the key, once the prefix is added
            accepted("bob", "nh", "a.b - a.c"),  # an alias
            accepted("carol", "near_highs", "a.b + a.c"),  # nearly the key: no match
        ]
    )
    by = {r.expression: r.backlog_key for r in load_accepted_formulas(ctx, ADMIN, SINCE, TODAY)}
    assert by == {"a.b / a.c": "near_high", "a.b - a.c": "near_high", "a.b + a.c": ""}


def test_a_draft_prefixed_feature_name_matches_its_backlog_key() -> None:
    ctx = stores([accepted("alice", "draft_near_high", "a.b / a.c")])
    (row,) = load_accepted_formulas(ctx, ADMIN, SINCE, TODAY)
    assert row.backlog_key == "near_high"
