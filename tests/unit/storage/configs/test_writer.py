"""ConfigWriter: drafts, immutable versions and user features (file + memory)."""

import tomllib
from pathlib import Path
from typing import Any

import pytest

from algotrade.core.model.errors import ConfigurationError
from algotrade.storage.configs.writer import (
    FileConfigWriter,
    MemoryConfigWriter,
    VersionExistsError,
    toml_text,
)

DOC: dict[str, Any] = {
    "id": "mine",
    "kind": "screener",
    "impl": "rules",
    "selection": "all_active",
    "criteria": {"price": {"field": "x", "op": "gt", "value": 5.0, "mode": "hard"}},
    "flags": {"f": {"all": [{"field": "a", "op": "in", "value": ["X", "Y"]}]}},
    "weird key": 1.5,
}


@pytest.fixture(params=["file", "memory"])
def writer(request: pytest.FixtureRequest, tmp_path: Path) -> FileConfigWriter | MemoryConfigWriter:
    return FileConfigWriter(tmp_path) if request.param == "file" else MemoryConfigWriter()


def test_toml_text_round_trips_and_fails_closed() -> None:
    assert tomllib.loads(toml_text(DOC)) == DOC
    with pytest.raises(ConfigurationError, match="null"):
        toml_text({"a": None})
    with pytest.raises(ConfigurationError, match="not a config value"):
        toml_text({"a": [object()]})
    with pytest.raises(ConfigurationError, match="larger"):
        toml_text({"a": "x" * 70_000})


def test_draft_save_load_discard(writer: Any) -> None:
    assert writer.draft("alice", "mine") is None
    writer.save_draft("alice", "mine", DOC)
    assert writer.draft("alice", "mine") == DOC
    assert writer.load("alice", "screeners", "mine") is None  # a draft never runs
    assert writer.names("alice", "screeners") == []
    assert writer.drafts("alice") == ["mine"] and writer.drafts("bob") == []
    assert writer.discard_draft("alice", "mine") is True
    assert writer.discard_draft("alice", "mine") is False
    assert writer.drafts("alice") == []


def test_versions_are_immutable_and_latest_wins(writer: Any) -> None:
    writer.add_version("alice", "mine", 1, DOC | {"version": 1})
    writer.add_version("alice", "mine", 2, DOC | {"version": 2, "impl": "rules"})
    with pytest.raises(VersionExistsError):
        writer.add_version("alice", "mine", 1, {"id": "other"})
    assert writer.version("alice", "mine", 1) == DOC | {"version": 1}
    assert writer.versions("alice", "mine") == [1, 2]
    assert writer.load("alice", "screeners", "mine") == DOC | {"version": 2}
    assert writer.names("alice", "screeners") == ["mine"]
    assert "alice" in writer.users()
    with pytest.raises(ConfigurationError, match="version"):
        writer.add_version("alice", "mine", 0, DOC)


def test_features_are_saved_per_theme(writer: Any) -> None:
    feature = {"f": {"expr": "a", "dtype": "float"}}
    writer.save_features("alice", "builder", feature)
    assert writer.load("alice", "features", "builder") == feature
    assert writer.names("alice", "features") == ["builder"]


@pytest.mark.parametrize("user", ["site", "../x", "Alice", "a/b", "a\n", ""])
def test_writes_are_user_scoped_with_strict_ids(writer: Any, user: str) -> None:
    with pytest.raises(ConfigurationError):
        writer.save_draft(user, "mine", DOC)
    with pytest.raises(ConfigurationError):
        writer.save_features(user, "builder", {})


@pytest.mark.parametrize("name", ["../mine", "mine.toml", "MINE", "mine\n"])
def test_screen_and_theme_ids_are_strict(writer: Any, name: str) -> None:
    with pytest.raises(ConfigurationError):
        writer.add_version("alice", name, 1, DOC)
    with pytest.raises(ConfigurationError):
        writer.save_features("alice", name, {})


def test_file_layout_and_atomicity(tmp_path: Path) -> None:
    writer = FileConfigWriter(tmp_path)
    writer.save_draft("alice", "mine", DOC)
    writer.add_version("alice", "mine", 1, DOC)
    screen = tmp_path / "users" / "alice" / "screeners" / "mine"
    assert sorted(p.name for p in screen.iterdir()) == ["draft.toml", "v1.toml"]
    before = (screen / "v1.toml").read_text()
    with pytest.raises(VersionExistsError):
        writer.add_version("alice", "mine", 1, {"id": "x"})
    assert (screen / "v1.toml").read_text() == before
    assert not list(screen.glob(".*.tmp"))  # no temp file left behind
    (screen / "v10.toml.bak").write_text("x")
    (screen / "v0.toml").write_text("x")
    assert writer.versions("alice", "mine") == [1]
    (tmp_path / "users" / "alice" / "screeners" / ".hidden").mkdir()
    assert writer.names("alice", "screeners") == ["mine"]
    assert writer.screen_dir("site", "mine") == tmp_path / "site" / "presets" / "screeners" / "mine"
    with pytest.raises(ConfigurationError, match="site"):
        writer.add_version("site", "mine", 1, DOC)  # site presets change by PR only
