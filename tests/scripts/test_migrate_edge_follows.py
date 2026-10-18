"""`scripts/migrate_edge_follows.py`: rewrites users' edge files from the old ``[follow]`` states
(ADR 0053 amendment 2026-10-10); a dry run writes nothing; only tmp config roots are touched."""

import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "migrate_edge_follows.py"
_spec = importlib.util.spec_from_file_location("migrate_edge_follows", SCRIPT)
assert _spec and _spec.loader
script = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(script)

SITE_EDGE = 'id = "drift"\n'
OLD_BOOKMARK = '[follow]\nstate = "following"\nsince = "2026-09-01"\n'
OLD_OWN = (
    'extends = "drift"\n\n[follow]\nstate = "trial"\nsince = "2026-09-02"\nreplaces = "drift"\n'
)


@pytest.fixture
def root(tmp_path: Path) -> Path:
    for user, name, text in (
        ("site", "drift", SITE_EDGE),
        ("alice", "drift", OLD_BOOKMARK),
        ("alice", "mine", OLD_OWN),
        ("bob", "drift", '[follow]\nstate = "retired"\nsince = "2026-09-01"\n'),
    ):
        folder = tmp_path / ("site" if user == "site" else f"users/{user}") / "edges"
        if user == "site":  # site/edges/<id>/edge.toml
            folder = folder / name
        folder.mkdir(parents=True, exist_ok=True)
        (folder / ("edge.toml" if user == "site" else f"{name}.toml")).write_text(text)
    return tmp_path


def snapshot(root: Path) -> dict[str, str]:
    return {str(p.relative_to(root)): p.read_text() for p in sorted(root.rglob("*.toml"))}


def test_a_dry_run_reports_and_writes_nothing(
    root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    before = snapshot(root)
    assert script.main(["--all", "--dry-run", "--config-dir", str(root)]) == 0
    out = capsys.readouterr().out
    assert "alice/drift: followed (dry run)" in out
    assert "alice/mine: status candidate (dry run)" in out
    assert "bob/drift: unfollowed (dry run)" in out
    assert snapshot(root) == before


def test_a_user_is_migrated_atomically_and_a_second_run_does_nothing(
    root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert script.main(["--user", "alice", "--config-dir", str(root)]) == 0
    files = snapshot(root)
    assert 'status = "candidate"' in files["users/alice/edges/mine.toml"]
    assert "[audit]" in files["users/alice/edges/mine.toml"]
    assert "state" not in files["users/alice/edges/drift.toml"]
    assert 'state = "retired"' in files["users/bob/edges/drift.toml"]  # not alice's: untouched
    capsys.readouterr()
    assert script.main(["--user", "alice", "--config-dir", str(root)]) == 0
    assert "nothing to migrate" in capsys.readouterr().out
    assert snapshot(root) == files


def test_all_users_are_migrated_and_a_retired_bookmark_is_archived(root: Path) -> None:
    assert script.main(["--all", "--config-dir", str(root)]) == 0
    assert not (root / "users" / "bob" / "edges" / "drift.toml").exists()
    assert list((root / "users" / "bob" / "archive" / "edges").glob("drift-*.toml"))
