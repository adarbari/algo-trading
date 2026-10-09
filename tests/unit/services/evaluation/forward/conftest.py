"""A store for the paper-record tests: the harness's small world (20 names, the rule screen
``momo``, two-session outcomes) and a user ``u1`` who follows the edge ``drift`` from the first
session."""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import pytest

from algotrade.config.user import UserContext
from algotrade.storage.configs.files import MemoryConfigStore
from tests.unit.services.evaluation.cross_section.conftest import (
    DAYS,
    World,
    build_world,
    edge_document,
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
