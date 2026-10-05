"""The configs a user sees: site presets then their own, resolved with a hash, or why not;
``resolved_for`` maps an unknown config to ``NotFoundError``."""

import tomllib
from datetime import date

import pytest

from algotrade.config.user import SITE_USER, UserContext
from algotrade.core.model.errors import ConfigurationError
from algotrade.services.read.context import NotFoundError, ReadContext, ResultCache
from algotrade.services.read.ops.configs import configs_of, load_configs, resolved_for
from algotrade.services.read.session import Session
from algotrade.storage.configs.files import MemoryConfigStore

SELECTION = """name = "all_active"
[where]
all = [{field = "instrument.status", op = "eq", value = "ACTIVE"}]
"""
SCREEN = """id = "vrp"
kind = "screener"
impl = "rules"
version = 1
selection = "all_active"

[criteria.price]
field = "rollup.price_stats@v2.close"
op = "gt"
value = 5
"""


@pytest.fixture
def store() -> MemoryConfigStore:
    return MemoryConfigStore(
        {
            ("site", "selections", "all_active"): tomllib.loads(SELECTION),
            ("site", "screeners", "vrp@1"): tomllib.loads(SCREEN),
            ("alice", "strategies", "broken"): {"id": "broken", "kind": "strategy"},
        }
    )


def test_presets_then_the_users_own(store: MemoryConfigStore) -> None:
    day = date(2026, 10, 1)
    session = Session(day, None, True, day, day, False, (), ())
    alice = UserContext("alice")
    ctx = ReadContext(None, store, alice, session, None, ResultCache())  # type: ignore[arg-type]
    found = load_configs(ctx)
    assert [(c.config_id, c.scope) for c in found] == [("vrp", "site"), ("broken", "alice")]
    vrp, broken = found
    assert (vrp.kind, vrp.impl, vrp.selection, vrp.error) == (
        "screener",
        "rules",
        "all_active",
        None,
    )
    assert vrp.hash and len(vrp.hash) == 64
    assert broken.kind is None and broken.hash is None and broken.error
    assert [c.config_id for c in load_configs(ctx, "screener")] == ["vrp"]
    assert [c.config_id for c in configs_of(store, UserContext(SITE_USER))] == ["vrp"]


def test_resolved_for(store: MemoryConfigStore) -> None:
    assert resolved_for(store, UserContext("alice"), "vrp").config.kind == "screener"
    with pytest.raises(NotFoundError):
        resolved_for(store, UserContext("alice"), "nope")
    with pytest.raises(ConfigurationError):
        resolved_for(store, UserContext("alice"), "broken")
