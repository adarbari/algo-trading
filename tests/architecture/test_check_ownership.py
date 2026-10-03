"""Unit tests for the guardrail scripts (ADR 0019) on synthetic trees: hits inside the owner
pass, hits outside fail, and stale ratchet entries fail so the lists only shrink."""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

from tests.conftest import REPO_ROOT


def _load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / "scripts" / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # dataclasses need the module registered
    spec.loader.exec_module(module)
    return module


checker = _load("check_ownership")
dupes = _load("check_dupes")

REGISTRY = """
[[responsibility]]
id = "snapshot-selection"
description = "pick the snapshot"
owner = ["src/pkg/owner.py"]
target_owner = ["src/pkg/data/*"]
section = "docs/x.md#r1"
detect = [
    { call = "latest_date" },
    { attr = "os.environ" },
    { import = "urllib.request" },
    { string_prefix = "EQ:" },
    { call = "load", arg = "site" },
    { call_regex = "(^|\\\\.)ingest_[a-z]+$" },
    { string = "nasdaqlisted" },
]
"""


def _tree(tmp_path: Path, files: dict[str, str], known: str = "") -> Path:
    (tmp_path / "architecture").mkdir()
    (tmp_path / "architecture" / "ownership.toml").write_text(REGISTRY)
    if known:
        (tmp_path / "architecture" / "known_violations.toml").write_text(known)
    for rel, text in files.items():
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(text)
    return tmp_path


def test_hit_inside_owner_or_target_owner_passes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _tree(tmp_path, {
        "src/pkg/owner.py": '"""Owner."""\nreader.latest_date("t", on_or_before=d)\n',
        "src/pkg/data/reference.py": '"""Target."""\nlatest_date("t")\n',
        "apps/app/clean.py": '"""Docstrings never count: EQ:ABC."""\nx = "EQ"\n',
    })  # fmt: skip
    assert checker.main(["--root", str(root)]) == 0
    assert "ownership: OK" in capsys.readouterr().out


def test_every_rule_kind_flags_a_hit_outside_the_owner(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = (
        "import os\nimport urllib.request\n"
        "reader.latest_date('t')\nkey = os.environ.get('K')\nid_ = f'EQ:{x}'\n"
        "configs.load('site', 'settings', 'universe')\nconfigs.load('user', 'x')\n"
        "jobs.ingest_bars()\nname = 'nasdaqlisted'\n"
    )
    root = _tree(tmp_path, {"apps/app/rogue.py": code})
    assert checker.main(["--root", str(root)]) == 1
    out = capsys.readouterr().out
    assert "[snapshot-selection] apps/app/rogue.py: 7 hit(s), 0 allowed" in out
    assert "owner: src/pkg/owner.py" in out and "see: docs/x.md#r1" in out
    hits = checker.scan(root, checker.load_registry(root))
    assert [h.line for h in hits] == [2, 3, 4, 5, 6, 8, 9]


def test_known_violations_allow_todays_hits_but_not_more(tmp_path: Path) -> None:
    known = '[[violation]]\nresponsibility = "snapshot-selection"\nfile = "apps/a.py"\ncount = 1\n'
    root = _tree(tmp_path, {"apps/a.py": "latest_date()\n"}, known)
    assert checker.main(["--root", str(root)]) == 0
    (root / "apps/a.py").write_text("latest_date()\nlatest_date()\n")
    assert checker.main(["--root", str(root)]) == 1


def test_stale_known_violation_fails_until_removed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    known = '[[violation]]\nresponsibility = "snapshot-selection"\nfile = "apps/a.py"\ncount = 2\n'
    root = _tree(tmp_path, {"apps/a.py": "latest_date()\n"}, known)
    assert checker.main(["--root", str(root)]) == 1
    assert "listed 2, found 1" in capsys.readouterr().out
    assert checker.main(["--root", str(root), "--update"]) == 0  # shrink the ratchet
    assert "count = 1" in (root / "architecture/known_violations.toml").read_text()
    assert checker.main(["--root", str(root), "--summary"]) == 0


def test_update_refuses_to_grow_the_ratchet(tmp_path: Path) -> None:
    root = _tree(tmp_path, {"apps/a.py": "latest_date()\n"})
    assert checker.main(["--root", str(root), "--update"]) == 1
    assert not (root / "architecture/known_violations.toml").exists()


def test_unknown_responsibility_in_ratchet_fails(tmp_path: Path) -> None:
    known = '[[violation]]\nresponsibility = "gone"\nfile = "apps/a.py"\ncount = 1\n'
    root = _tree(tmp_path, {"apps/a.py": "x = 1\n"}, known)
    _, stale = checker.compare([], checker.load_known(root), checker.load_registry(root))
    assert any("gone" in s and "not a responsibility" in s for s in stale)


def test_a_detect_rule_needs_exactly_one_kind(tmp_path: Path) -> None:
    root = _tree(tmp_path, {})
    (root / "architecture/ownership.toml").write_text(
        REGISTRY.replace('{ call = "latest_date" }', '{ call = "a", attr = "b" }')
    )
    with pytest.raises(ValueError, match="exactly one"):
        checker.load_registry(root)


# ----------------------------------------------------------------------------- dupes


def test_dupes_counts_pylint_blocks() -> None:
    output = "x.py:1:0: R0801: Similar lines in 2 files\ny.py:1:0: R0801: Similar lines in 3 files"
    assert dupes.count_blocks(output) == 2
    assert dupes.count_blocks("") == 0


@pytest.mark.parametrize(
    ("found", "baseline", "code", "word"),
    [(2, 2, 0, "OK"), (3, 2, 1, "Extract"), (1, 2, 1, "lower")],
)
def test_dupes_ratchet_fails_when_count_moves_either_way(
    found: int, baseline: int, code: int, word: str
) -> None:
    result, message = dupes.verdict(found, baseline)
    assert result == code and word in message
