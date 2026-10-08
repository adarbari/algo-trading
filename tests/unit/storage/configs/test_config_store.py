from pathlib import Path

import pytest

from algotrade.config.user import SITE_USER, UserContext
from algotrade.core.model.errors import ConfigurationError
from algotrade.services.configs import nightly_screeners, resolve_config
from algotrade.storage.configs.files import FileConfigStore, MemoryConfigStore
from algotrade.storage.configs.store import OverlayConfigStore
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


def test_the_nightly_runs_every_site_and_user_screener(root: Path) -> None:
    runs = [(r.user.user_id, r.config.id) for r in nightly_screeners(FileConfigStore(root))]
    assert runs == [(SITE_USER, "scr"), ("alice", "scr")]  # alice's "mine" is a strategy


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


def test_the_guide_files_are_site_only(root: Path) -> None:
    (root / "site" / "guide").mkdir()
    (root / "site" / "guide" / "sections.toml").write_text('[[section]]\nid = "fields"\n')
    (root / "users" / "alice" / "guide").mkdir()
    (root / "users" / "alice" / "guide" / "sections.toml").write_text("x = 1\n")
    store = FileConfigStore(root)
    assert store.names("site", "guide") == ["sections"]
    assert store.load("site", "guide", "sections") == {"section": [{"id": "fields"}]}
    assert store.load("alice", "guide", "sections") is None  # never a user's


def test_the_guide_playbooks_are_site_only_under_the_guide_folder(root: Path) -> None:
    (root / "site" / "guide" / "playbooks").mkdir(parents=True)
    (root / "site" / "guide" / "playbooks" / "pullback.toml").write_text('id = "pullback"\n')
    (root / "site" / "guide" / "sections.toml").write_text("")
    store = FileConfigStore(root)
    assert store.names("site", "guide_playbooks") == ["pullback"]
    assert store.names("site", "guide") == ["sections"]  # the subfolder is not a guide file
    assert store.load("site", "guide_playbooks", "pullback") == {"id": "pullback"}
    assert store.load("alice", "guide_playbooks", "pullback") is None  # never a user's


def test_screen_documents_are_read_through_every_store(tmp_path: Path) -> None:
    """Drafts and versions are read through the ``ConfigStore`` (the read model reads them;
    only the writer writes them): files, memory and an overlay over either."""
    screen = tmp_path / "users" / "alice" / "screeners" / "mine"
    screen.mkdir(parents=True)
    (screen / "draft.toml").write_text('id = "mine"\n')
    (screen / "v1.toml").write_text('id = "mine"\nversion = 1\n')
    files = FileConfigStore(tmp_path)
    assert (files.drafts("alice"), files.versions("alice", "mine")) == (["mine"], [1])
    assert files.draft("alice", "mine") == {"id": "mine"}
    assert files.version("alice", "mine", 1) == {"id": "mine", "version": 1}
    assert (files.draft(SITE_USER, "mine"), files.drafts(SITE_USER)) == (None, [])
    with pytest.raises(ConfigurationError):
        files.version("alice", "mine", 0)
    memory = MemoryConfigStore({("alice", "screeners", "mine@2"): {"id": "mine", "version": 2}})
    assert (memory.draft("alice", "mine"), memory.drafts("alice")) == (None, [])
    assert memory.versions("alice", "mine") == [2]
    assert memory.version("alice", "mine", 2) == {"id": "mine", "version": 2}
    assert memory.version("alice", "mine", 1) is None
    overlay = OverlayConfigStore(files, {})
    assert (overlay.drafts("alice"), overlay.versions("alice", "mine")) == (["mine"], [1])
    assert overlay.draft("alice", "mine") == files.draft("alice", "mine")
    assert overlay.version("alice", "mine", 1) == files.version("alice", "mine", 1)


def test_a_users_identity_is_one_file_in_their_folder(root: Path) -> None:
    (root / "users" / "alice" / "identity.toml").write_text('email = "alice@example.com"\n')
    store = FileConfigStore(root)
    assert store.load("alice", "identity", "identity") == {"email": "alice@example.com"}
    assert store.load("bob", "identity", "identity") is None
    assert store.load(SITE_USER, "identity", "identity") is None  # a user's, never the site's


def test_a_local_site_file_overlays_the_committed_one(tmp_path: Path) -> None:
    site = tmp_path / "site"
    site.mkdir()
    (site / "llm.toml").write_text('enabled = false\nmodel = "a"\n[request]\nx = 1\ny = 2\n')
    store = FileConfigStore(tmp_path)
    assert store.load("site", "settings", "llm") == {
        "enabled": False, "model": "a", "request": {"x": 1, "y": 2},
    }  # fmt: skip
    (site / "llm.local.toml").write_text("enabled = true\n[request]\ny = 3\n")
    assert store.load("site", "settings", "llm") == {
        "enabled": True, "model": "a", "request": {"x": 1, "y": 3},
    }  # fmt: skip
    assert store.names("site", "settings") == ["llm"]  # never ``llm.local``
    assert FileConfigStore(tmp_path, local=False).load("site", "settings", "llm") == {
        "enabled": False, "model": "a", "request": {"x": 1, "y": 2},
    }  # fmt: skip


def test_only_allowlisted_settings_take_a_local_file(tmp_path: Path) -> None:
    site = tmp_path / "site"
    site.mkdir()
    (site / "users.toml").write_text('[[user]]\nid = "a"\nrole = "trader"\n')
    (site / "users.local.toml").write_text('[[user]]\nid = "root"\nrole = "admin"\n')
    assert FileConfigStore(tmp_path).load("site", "settings", "users") == {
        "user": [{"id": "a", "role": "trader"}]
    }
