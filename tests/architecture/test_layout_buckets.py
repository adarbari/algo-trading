"""Fitness tests: tests, config and docs are bucketed like the code (ADR 0020).

- ``tests/``: a directory under a ``[[test_mirror]]`` root mirrors a declared source directory
  that exists; every other test directory is a declared ``[[test_dir]]``; at most
  ``max_modules`` modules per test directory (``__init__.py`` and ``conftest.py`` excluded);
  ``holds = "folders"`` has no modules, ``holds = "data"`` no Python;
- ``config/`` and ``docs/``: every folder is declared with a purpose and holds at most
  ``max_files`` files (``kind = "log"`` excepted: the ADR log is append-only);
- every ``config/site/*.toml`` (and ``overrides/*.csv``) is loaded by the one settings loader.
  That every key in it is read by code: ``test_ownership.py::
  test_every_site_setting_key_is_read_by_code``.
"""

import ast
import fnmatch
import tomllib
from collections.abc import Collection, Iterator
from pathlib import Path, PurePosixPath
from typing import Any

import pytest

from tests.conftest import REPO_ROOT

LAYOUT_FILE = "architecture/layout.toml"
LAYOUT: dict[str, Any] = tomllib.loads((REPO_ROOT / LAYOUT_FILE).read_text())
GUIDE = "CLAUDE.md 'Directory layout' (where does this go) and .claude/skills/add-responsibility"
SOURCE_DIRS = [d["path"] for d in LAYOUT["dir"]]
MIRRORS: list[dict[str, str]] = LAYOUT["test_mirror"]
TEST_DIRS: list[dict[str, Any]] = LAYOUT["test_dir"]
SETTINGS_LOADER = "src/algotrade/config/site/settings.py"
SKIPPED = {"__pycache__", "node_modules"}


def _rel(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def _matches(directory: str, pattern: str) -> bool:
    """``*`` matches exactly one path segment."""
    parts, wanted = PurePosixPath(directory).parts, PurePosixPath(pattern).parts
    return len(parts) == len(wanted) and all(map(fnmatch.fnmatchcase, parts, wanted))


def _declared(directory: str, decls: list[dict[str, Any]]) -> dict[str, Any] | None:
    """The most specific declaration matching ``directory`` (exact path beats a glob)."""
    found = [d for d in decls if _matches(directory, d["path"])]
    return min(found, key=lambda d: d["path"].count("*"), default=None)


def _walk(top: str, skip: Collection[str] = ()) -> Iterator[Path]:
    """``top`` and every directory below it (hidden, cache and ``skip`` subtrees left out)."""
    root = REPO_ROOT / top
    if not root.is_dir():
        return
    for path in [root, *sorted(root.rglob("*"))]:
        rel = _rel(path)
        if not path.is_dir() or any(p in SKIPPED or p.startswith(".") for p in Path(rel).parts):
            continue
        if not any(rel == s or rel.startswith(s + "/") for s in skip):
            yield path


def _files(directory: Path) -> list[Path]:
    return [p for p in directory.iterdir() if p.is_file() and not p.name.startswith(".")]


def _test_modules(directory: Path) -> list[str]:
    return sorted(
        p.name for p in directory.glob("*.py") if p.name not in ("__init__.py", "conftest.py")
    )


# ----------------------------------------------------------------------------- the registry


def test_bucket_declarations_are_well_formed_and_not_stale() -> None:
    assert 0 < LAYOUT["warn_modules"] < LAYOUT["max_modules"], "warn_modules < max_modules"
    for mirror in MIRRORS:
        assert mirror["source"] in SOURCE_DIRS, f"[[test_mirror]] {mirror}: undeclared source"
    for table in ("test_dir", "config_dir", "docs_dir"):
        decls = LAYOUT[table]
        paths = [d["path"] for d in decls]
        assert len(paths) == len(set(paths)), f"duplicate [[{table}]] paths"
        for decl in decls:
            assert decl.get("purpose"), f"[[{table}]] {decl['path']}: needs a one-line purpose"
            assert decl.get("holds") in (None, "tests", "folders", "data"), decl
            assert decl.get("kind") in (None, "log"), decl
            exists = any(_matches(_rel(d), decl["path"]) for d in _walk(decl["path"].split("/")[0]))
            assert exists or decl.get("local"), (
                f"[[{table}]] {decl['path']} does not exist: remove it from {LAYOUT_FILE}"
            )


# ----------------------------------------------------------------------------- tests/


def _mirror_of(directory: str) -> tuple[dict[str, str], str] | None:
    """(the mirror, the source directory) for a test directory under a mirror root."""
    for mirror in MIRRORS:
        if directory == mirror["tests"] or directory.startswith(mirror["tests"] + "/"):
            return mirror, mirror["source"] + directory[len(mirror["tests"]) :]
    return None


TEST_TREE = [_rel(d) for d in _walk("tests")]


def test_every_test_directory_is_a_mirror_or_a_declared_bucket() -> None:
    stray, unmirrored = [], []
    for directory in TEST_TREE:
        mirrored = _mirror_of(directory)
        if mirrored is None:
            if _declared(directory, TEST_DIRS) is None:
                stray.append(directory)
            continue
        source = mirrored[1]
        known = (REPO_ROOT / source).is_dir() and any(_matches(source, p) for p in SOURCE_DIRS)
        if not known:
            unmirrored.append(f"{directory} (no declared source directory {source})")
    problems = []
    if stray:
        problems.append(
            f"undeclared test directories {stray}: mirror the source under a [[test_mirror]] "
            "root, or declare the bucket as a [[test_dir]] with a purpose"
        )
    if unmirrored:
        problems.append(
            f"test directories that mirror no source directory {unmirrored}: tests mirror "
            "their source ([[test_mirror]]); move them to the folder of the code they test"
        )
    assert not problems, f"{'; '.join(problems)} ({LAYOUT_FILE}; see {GUIDE})"


def test_test_directories_hold_at_most_max_modules() -> None:
    limit = LAYOUT["max_modules"]
    over = {
        d: n for d in TEST_TREE if (n := len(_test_modules(REPO_ROOT / d))) > limit
    }  # fmt: skip
    assert not over, (
        f"test directories with more than {limit} modules (split by kind into declared "
        f"subfolders, mirroring the source; {LAYOUT_FILE}, {GUIDE}): {over}"
    )


def test_test_buckets_hold_what_they_declare() -> None:
    wrong = []
    for directory in TEST_TREE:
        decl = _declared(directory, TEST_DIRS) if _mirror_of(directory) is None else None
        holds = (decl or {}).get("holds", "tests")
        path = REPO_ROOT / directory
        if holds == "folders" and _test_modules(path):
            wrong.append(f"{directory} holds folders only, found {_test_modules(path)}")
        if holds == "data" and list(path.glob("*.py")):
            wrong.append(f"{directory} holds recorded data only (no Python)")
    assert not wrong, f"{wrong}: move the modules into a declared bucket ({LAYOUT_FILE}; {GUIDE})"


# ----------------------------------------------------------------------------- config/, docs/


@pytest.mark.parametrize("table", ["config_dir", "docs_dir"])
def test_config_and_docs_folders_are_declared_and_small(table: str) -> None:
    decls: list[dict[str, Any]] = LAYOUT[table]
    top = decls[0]["path"].split("/")[0]
    local = {d["path"] for d in decls if d.get("local")}
    limit = LAYOUT["max_files"]
    undeclared, over = [], {}
    for path in _walk(top, skip=local):
        directory = _rel(path)
        decl = _declared(directory, decls)
        if decl is None:
            undeclared.append(directory)
        elif decl.get("kind") != "log" and (n := len(_files(path))) > limit:
            over[directory] = n
    assert not undeclared, (
        f"undeclared {top}/ folders {undeclared}: declare each as a [[{table}]] in "
        f"{LAYOUT_FILE} with a purpose; see {GUIDE}"
    )
    assert not over, (
        f"{top}/ folders with more than {limit} files {over}: split by kind into subfolders "
        f"declared as [[{table}]] in {LAYOUT_FILE}; see {GUIDE}"
    )


def _loaded_site_names() -> tuple[set[str], set[str]]:
    """``config/site`` documents and overrides the settings loader names (string literals
    passed to ``site_document`` / ``load(...)`` and ``overrides``)."""
    documents: set[str] = set()
    overrides: set[str] = set()
    for node in ast.walk(ast.parse((REPO_ROOT / SETTINGS_LOADER).read_text())):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
        literals = [
            a.value for a in node.args if isinstance(a, ast.Constant) and isinstance(a.value, str)
        ]
        if not literals:
            continue
        if name in ("site_document", "load"):
            documents.add(literals[-1])
        elif name == "overrides":
            overrides.add(literals[-1])
    return documents, overrides


def test_every_site_settings_file_is_loaded_by_the_settings_loader() -> None:
    documents, overrides = _loaded_site_names()
    site = REPO_ROOT / "config" / "site"
    unknown = sorted(
        p.name for p in site.glob("*.toml") if p.stem not in documents and ".local" not in p.stem
    )
    unknown += sorted(
        f"overrides/{p.name}" for p in (site / "overrides").glob("*") if p.stem not in overrides
    )
    assert not unknown, (
        f"config/site files no loader reads {unknown}: load and type each in {SETTINGS_LOADER} "
        "(the one settings loader), or delete it"
    )
