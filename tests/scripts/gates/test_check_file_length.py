"""check_file_length lists files near the cap as warnings without failing, and the commit
hooks refuse a leftover merge-conflict marker (2026-10-18 session review)."""

from pathlib import Path

from scripts import check_file_length as cfl

ROOT = Path(__file__).resolve().parents[3]


def _file(tmp_path: Path, name: str, lines: int) -> Path:
    path = tmp_path / name
    path.write_text("x = 1\n" * lines)
    return path


def test_floor_lists_files_near_the_cap_and_the_default_only_those_over(tmp_path: Path) -> None:
    near, over = _file(tmp_path, "near.py", 950), _file(tmp_path, "over.py", 1001)
    small = _file(tmp_path, "small.py", 10)
    paths = [near, over, small]
    assert [p.name for p, _ in cfl.oversized(paths, 1000)] == ["over.py"]
    assert [p.name for p, _ in cfl.oversized(paths, 1000, 900)] == ["near.py", "over.py"]


def test_the_commit_hooks_refuse_a_leftover_conflict_marker() -> None:
    config = (ROOT / ".pre-commit-config.yaml").read_text()
    assert "id: check-merge-conflict" in config
