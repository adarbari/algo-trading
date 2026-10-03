from pathlib import Path

import pytest

from algotrade.config.user import SITE_USER, UserContext
from algotrade.core.model.errors import ConfigurationError
from algotrade.services.configs import resolve_config, scheduled
from algotrade.storage.configs.files import FileConfigStore
from algotrade.storage.factory import open_config_store
from tests.conftest import REPO_ROOT

SELECTION = """name = "all_active"
[where]
all = [{field = "instrument.status", op = "eq", value = "ACTIVE"}]
"""
SITE_SCREENER = """id = "scr"
kind = "screener"
impl = "short_premium_liquidity"
selection = "all_active"
schedule = "nightly"
"""
USER_STRATEGY = """id = "mine"
kind = "strategy"
impl = "buy_and_hold"
selection = "all_active"
"""


@pytest.fixture
def root(tmp_path: Path) -> Path:
    site, alice = tmp_path / "site", tmp_path / "users" / "alice" / "strategies"
    for directory in (site / "presets" / "strategies", site / "presets" / "selections", alice):
        directory.mkdir(parents=True)
    (site / "defaults.toml").write_text("[screening]\nmin_coverage = 0.5\n")
    (site / "presets" / "selections" / "all_active.toml").write_text(SELECTION)
    (site / "presets" / "strategies" / "scr.toml").write_text(SITE_SCREENER)
    (alice / "scr.toml").write_text('exports = ["legacy_liquidity_csv"]\n')
    (alice / "mine.toml").write_text(USER_STRATEGY)
    return tmp_path


def test_file_store_reads_layers(root: Path) -> None:
    store = FileConfigStore(root)
    assert store.users() == ["alice"]
    assert store.names("site", "strategies") == ["scr"]
    assert store.names("alice", "strategies") == ["mine", "scr"]
    assert store.names("site", "defaults") == ["defaults"]
    assert store.names("alice", "defaults") == []
    assert store.load("alice", "defaults", "defaults") is None
    assert store.load("site", "strategies", "nope") is None
    resolved = resolve_config(store, "scr", UserContext("alice"))
    assert resolved.config.exports == ("legacy_liquidity_csv",)
    assert resolved.settings["screening"]["min_coverage"] == 0.5


def test_scheduled_runs_site_and_user_configs(root: Path) -> None:
    runs = [(r.user.user_id, r.config.id) for r in scheduled(FileConfigStore(root))]
    assert runs == [(SITE_USER, "scr"), ("alice", "scr")]  # alice's "mine" has no schedule


def test_invalid_toml_and_unsafe_ids(root: Path) -> None:
    (root / "site" / "presets" / "strategies" / "broken.toml").write_text("id = \n")
    store = FileConfigStore(root)
    with pytest.raises(ConfigurationError, match="invalid TOML"):
        store.load("site", "strategies", "broken")
    with pytest.raises(ConfigurationError, match="invalid user id"):
        store.load("../etc", "strategies", "x")
    with pytest.raises(ConfigurationError, match="unknown config kind"):
        store.load("site", "secrets", "x")
    assert FileConfigStore(root / "missing").users() == []
    assert FileConfigStore(root / "missing").names("site", "strategies") == []


def test_every_repo_config_resolves_against_the_catalogue() -> None:
    store = open_config_store(str(REPO_ROOT / "config"))
    names = store.names("site", "strategies")
    assert names, "the repo ships site presets"
    for name in names:
        resolve_config(store, name, UserContext(SITE_USER))


def test_site_settings_and_overrides(root: Path) -> None:
    (root / "site" / "universe.toml").write_text('source = "nasdaq_trader"\n')
    (root / "site" / "overrides").mkdir()
    (root / "site" / "overrides" / "leveraged_etfs.csv").write_text(
        "symbol,leverage,tracks\n# a comment, with commas\nTQQQ,3,Nasdaq-100\n\n"
    )
    store = FileConfigStore(root)
    assert store.load("site", "settings", "universe") == {"source": "nasdaq_trader"}
    assert store.load("alice", "settings", "universe") is None
    assert store.names("site", "settings") == ["universe"]
    assert store.names("alice", "settings") == []
    assert store.overrides("leveraged_etfs") == [
        {"symbol": "TQQQ", "leverage": "3", "tracks": "Nasdaq-100"}
    ]
    assert store.overrides("missing") == []
