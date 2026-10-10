"""scripts/layout_report.py: the layout registry is read as one, merged across its files."""

import importlib.util
from pathlib import Path

import pytest

from tests.conftest import REPO_ROOT

_spec = importlib.util.spec_from_file_location(
    "layout_report", REPO_ROOT / "scripts" / "layout_report.py"
)
assert _spec and _spec.loader
layout_report = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(layout_report)


def _write(root: Path, name: str, text: str) -> None:
    (root / "architecture").mkdir(exist_ok=True)
    (root / "architecture" / name).write_text(text)


def test_entry_lists_concatenate_and_settings_come_from_their_one_file(tmp_path: Path) -> None:
    _write(tmp_path, "layout.toml", 'max_modules = 10\n[[dir]]\npath = "src"\n')
    _write(tmp_path, "layout_tests.toml", '[[dir]]\npath = "apps"\n[[test_dir]]\npath = "t"\n')
    _write(tmp_path, "web_layout.toml", '[[dir]]\npath = "not-read"\n')
    layout = layout_report.read_layout(tmp_path)
    assert layout["max_modules"] == 10
    assert [d["path"] for d in layout["dir"]] == ["src", "apps"]
    assert [d["path"] for d in layout["test_dir"]] == ["t"]


def test_a_setting_in_two_files_is_refused(tmp_path: Path) -> None:
    _write(tmp_path, "layout.toml", "max_modules = 10\n")
    _write(tmp_path, "layout_tests.toml", "max_modules = 12\n")
    with pytest.raises(ValueError, match=r"max_modules is set in both layout\.toml"):
        layout_report.read_layout(tmp_path)


def test_no_registry_file_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="no layout registry"):
        layout_report.read_layout(tmp_path)


def test_the_repo_registry_is_split_and_every_file_is_read() -> None:
    files = sorted(p.name for p in (REPO_ROOT / "architecture").glob("layout*.toml"))
    assert len(files) > 1, files
    layout = layout_report.read_layout(REPO_ROOT)
    assert {"dir", "test_mirror", "test_dir", "config_dir", "docs_dir"} <= layout.keys()
