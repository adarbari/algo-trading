"""A store for the paper-record tests: the harness's small world (20 names, the rule screen
``momo``, two-session outcomes) and a user ``u1`` who follows the edge ``drift`` from the first
session."""

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest

from algotrade.config.user import UserContext
from algotrade.storage.configs.files import MemoryConfigStore
from tests.unit.services.evaluation.cross_section.conftest import (
    DAYS,
    IDS,
    World,
    build_world,
    edge_document,
    with_listing_history,
)

USER = UserContext("u1")
NOW = datetime(2026, 10, 5, 22, tzinfo=UTC)  # after every outcome of the world was known


@dataclass
class Desk:
    """The world with ``u1``'s own edge document over the site's presets."""

    world: World
    configs: MemoryConfigStore


def desk(world: World | None = None, **changes: Any) -> Desk:
    w = world or build_world()
    follow = {"state": "following", "since": DAYS[0].isoformat()}
    doc = edge_document(follow=changes.pop("follow", follow), **changes)
    docs = {**w.configs._docs, ("u1", "edges", "drift"): doc}
    return Desk(w, MemoryConfigStore(docs))


@pytest.fixture
def following() -> Desk:
    return desk()


def event_world(days_with: dict[date, list[int]]) -> World:
    """The world where names ``i`` have the earnings reaction on a decision session. The listing
    history is stored: an event schedule reads back before the first session (the dedupe)."""
    w = with_listing_history(build_world(), DAYS[0] - timedelta(days=3))
    for day, names in days_with.items():
        w.write_reactions(day, {IDS[i]: 0 for i in names})
    return w


def event_changes(horizon: int = 2) -> dict[str, Any]:
    """The edge document keys of an ``on_event:earnings_reaction`` edge over every name it finds."""
    outcome = {
        "kind": "excess_return", "horizon_sessions": [horizon], "benchmark": "SPY",
        "start_offset_sessions": 1,
    }  # fmt: skip
    return {"schedule": "on_event:earnings_reaction", "top_k": "all", "outcome": outcome}
