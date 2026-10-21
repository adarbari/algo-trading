"""ConfigWriter: drafts, immutable versions and user features (file + memory)."""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from algotrade.core.model.errors import ConfigurationError
from algotrade.storage.configs.generation import is_stable, writing
from algotrade.storage.configs.writer import (
    FileConfigWriter,
    MemoryConfigWriter,
    VersionExistsError,
    archive_name,
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


def test_delete_archives_the_draft_and_every_version(writer: Any) -> None:
    at = datetime(2026, 10, 5, 9, 30, tzinfo=UTC)
    assert writer.delete_screen("alice", "mine", at) is False
    writer.add_version("alice", "mine", 1, DOC | {"version": 1})
    writer.save_draft("alice", "mine", DOC)
    assert writer.delete_screen("alice", "mine", at) is True
    assert writer.names("alice", "screeners") == [] and writer.drafts("alice") == []
    assert writer.versions("alice", "mine") == [] and writer.draft("alice", "mine") is None
    assert writer.delete_screen("alice", "mine", at) is False
    assert writer.was_deleted("alice", "mine") and not writer.was_deleted("alice", "min")
    assert not writer.was_deleted("bob", "mine")


def test_a_deleted_screen_is_kept_in_the_archive(tmp_path: Path) -> None:
    writer = FileConfigWriter(tmp_path)
    writer.add_version("alice", "mine", 1, DOC | {"version": 1})
    writer.save_draft("alice", "mine", DOC)
    writer.delete_screen("alice", "mine", datetime(2026, 10, 5, 9, 30, tzinfo=UTC))
    kept = tmp_path / "users" / "alice" / "archive" / "screeners" / "mine-20261005T093000000000Z"
    assert sorted(p.name for p in kept.iterdir()) == ["draft.toml", "v1.toml"]
    assert not (tmp_path / "users" / "alice" / "screeners" / "mine").exists()
    assert writer.was_deleted("alice", "mine") and not FileConfigWriter(tmp_path).was_deleted(
        "bob", "mine"
    )
    assert archive_name("mine", datetime(2026, 10, 5, 9, 30, tzinfo=UTC)).startswith("mine-2026")
    with pytest.raises(ConfigurationError, match="timezone"):
        archive_name("mine", datetime(2026, 10, 5))  # noqa: DTZ001 - the naive case under test


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


def test_user_documents_are_saved_archived_and_their_ids_remembered(writer: Any) -> None:
    doc = {"extends": "drift", "follow": {"state": "following"}}
    writer.save_user_document("alice", "edges", "mine", doc)
    assert writer.load("alice", "edges", "mine") == doc
    assert writer.names("alice", "edges") == ["mine"]
    assert not writer.was_archived("alice", "edges", "mine")
    assert writer.archive_user_document("alice", "edges", "mine", datetime(2026, 10, 9, tzinfo=UTC))
    assert writer.load("alice", "edges", "mine") is None
    assert writer.was_archived("alice", "edges", "mine")
    assert not writer.was_archived("alice", "edges", "min")  # a prefix is another id
    assert not writer.archive_user_document("alice", "edges", "mine", datetime.now(UTC))


@pytest.mark.parametrize(
    ("user", "kind", "name"),
    [("site", "edges", "mine"), ("alice", "screeners", "mine"), ("alice", "edges", "../x")],
)
def test_user_documents_have_a_user_a_known_kind_and_a_strict_id(
    writer: Any, user: str, kind: str, name: str
) -> None:
    with pytest.raises(ConfigurationError):
        writer.save_user_document(user, kind, name, {})


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


def test_every_write_moves_the_users_generation_to_the_next_even_value(writer: Any) -> None:
    """ADR 0077 decision 15: the counter a cached answer is keyed on (file and memory alike)."""
    at = datetime(2026, 10, 5, 9, 30, tzinfo=UTC)
    assert writer.generation("alice") == 0
    calls = [
        lambda: writer.save_draft("alice", "mine", DOC),
        lambda: writer.add_version("alice", "mine", 1, DOC | {"version": 1}),
        lambda: writer.save_features("alice", "theme", {"features": {}}),
        lambda: writer.save_preferences("alice", {"ideas": {"priority": []}}),
        lambda: writer.save_user_document("alice", "edges", "e1", {"id": "e1"}),
        lambda: writer.archive_user_document("alice", "edges", "e1", at),
        lambda: writer.discard_draft("alice", "mine"),
        lambda: writer.delete_screen("alice", "mine", at),
    ]
    seen = [writer.generation("alice")]
    for call in calls:
        call()
        seen.append(writer.generation("alice"))
    assert all(g % 2 == 0 for g in seen) and seen == sorted(set(seen)), seen
    assert writer.generation("bob") == 0  # one user's write moves no other's


def test_a_failed_write_still_leaves_the_generation_even_and_moved(writer: Any) -> None:
    writer.add_version("alice", "mine", 1, DOC | {"version": 1})
    before = writer.generation("alice")
    with pytest.raises(VersionExistsError if isinstance(writer, FileConfigWriter) else Exception):
        writer.add_version("alice", "mine", 1, DOC | {"version": 1})
    assert writer.generation("alice") > before and writer.generation("alice") % 2 == 0


def test_the_generation_is_odd_during_a_write_and_a_crash_leaves_it_odd(tmp_path: Path) -> None:
    writer = FileConfigWriter(tmp_path)
    user_dir = tmp_path / "users" / "alice"
    with writing(user_dir):
        assert not is_stable(writer.generation("alice"))
    assert is_stable(writer.generation("alice"))
    (user_dir / ".generation").write_text("7")  # a process died mid write
    assert not is_stable(writer.generation("alice"))  # nothing is cached under it
    writer.save_preferences("alice", {"x": 1})
    assert writer.generation("alice") == 10  # the next write repairs it, to an even value
