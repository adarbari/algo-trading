"""`scripts/ops/merge_durations.py`: new timings overlay the old, unseen tests keep theirs,
tiny entries are dropped."""

import importlib.util
import json
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "ops" / "merge_durations.py"
spec = importlib.util.spec_from_file_location("merge_durations", SCRIPT)
assert spec and spec.loader
merge_durations = importlib.util.module_from_spec(spec)
spec.loader.exec_module(merge_durations)


def test_new_timings_win_and_unseen_tests_keep_theirs() -> None:
    merged = merge_durations.merge({"a": 1.0, "b": 2.0}, [{"a": 3.0}, {"c": 4.0}])
    assert merged == {"a": 3.0, "b": 2.0, "c": 4.0}


def test_tiny_entries_are_dropped() -> None:
    assert merge_durations.merge({}, [{"a": 0.01, "b": 0.5}]) == {"b": 0.5}


def test_main_merges_files_into_the_target(tmp_path: Path) -> None:
    (tmp_path / "x").mkdir()
    (tmp_path / "x" / ".durations-unit-c-1of6.json").write_text('{"t": 2.0}')
    target = tmp_path / ".test_durations"
    target.write_text('{"old": 1.0}')
    assert merge_durations.main(["", str(tmp_path), str(target)]) == 0
    assert json.loads(target.read_text()) == {"old": 1.0, "t": 2.0}


def test_main_fails_without_recorded_files(tmp_path: Path) -> None:
    assert merge_durations.main(["", str(tmp_path), str(tmp_path / "t")]) == 1
