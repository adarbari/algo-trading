"""Fitness tests for the web app's directory layout (ADR 0025, ``[[web_dir]]`` in
``architecture/layout.toml``).

- every directory under ``apps/web`` (build output and ``node_modules`` skipped) is declared;
- at most ``max_modules`` modules per directory (``index.ts``, tests, stories and ``.d.ts``
  are not modules) and no grab-bag module names (``utils.ts``, ``helpers.ts``, ...);
- ``kind = "layer"`` folders hold only folders and a README; a ``slice`` has a public
  ``index.ts``; a ``segment`` is named for its kind; a ``component`` has its source, styles,
  story, test, index and screenshots; ``screenshots`` hold only ``.png``;
- stylesheets only where ``styles = true`` (the design system).

Import rules between these folders are ESLint's (``apps/web/lint-rules/``); the per-story
completeness of design-system components is ``npm run ds:check``.
"""

import fnmatch
import tomllib
from pathlib import Path, PurePosixPath
from typing import Any

import pytest

from tests.conftest import REPO_ROOT

LAYOUT_FILE = "architecture/layout.toml"
LAYOUT: dict[str, Any] = tomllib.loads((REPO_ROOT / LAYOUT_FILE).read_text())
WEB: dict[str, Any] = LAYOUT["web"]
DIRS: list[dict[str, Any]] = LAYOUT["web_dir"]
GUIDE = "docs/ui/architecture.md (where it goes) and .claude/skills/add-web-page"
HINT = f"declare it as a [[web_dir]] in {LAYOUT_FILE} with a purpose; see {GUIDE}"
KINDS = (None, "layer", "slice", "segment", "component", "screenshots")
CODE_SUFFIXES = (".ts", ".tsx", ".js")
NOT_MODULES = ("index.ts", "*.test.*", "*.spec.*", "*.stories.*", "*.d.ts")
STYLE_SUFFIXES = (".css", ".scss", ".sass", ".less")
LAYER_FILES = {"README.md"}


def _rel(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def _walk() -> list[Path]:
    root = REPO_ROOT / WEB["root"]
    skipped = set(WEB["skipped"])
    found = [root]
    for path in sorted(root.rglob("*")):
        parts = path.relative_to(root).parts
        if not path.is_dir() or skipped & set(parts):
            continue
        if any(p.startswith(".") and p != ".storybook" for p in parts):
            continue
        found.append(path)
    return found


WEB_TREE = _walk() if (REPO_ROOT / WEB["root"]).is_dir() else []
WEB_DIRS = [_rel(d) for d in WEB_TREE]


def _matches(directory: str, pattern: str) -> bool:
    """``*`` matches exactly one path segment."""
    parts, wanted = PurePosixPath(directory).parts, PurePosixPath(pattern).parts
    return len(parts) == len(wanted) and all(map(fnmatch.fnmatchcase, parts, wanted))


def _declaration(directory: str) -> dict[str, Any] | None:
    """The most specific declaration matching ``directory`` (exact path beats a glob)."""
    found = [d for d in DIRS if _matches(directory, d["path"])]
    return min(found, key=lambda d: d["path"].count("*"), default=None)


def _files(directory: Path) -> list[Path]:
    return sorted(p for p in directory.iterdir() if p.is_file() and not p.name.startswith("."))


def _is_module(path: Path) -> bool:
    return path.suffix in CODE_SUFFIXES and not any(
        fnmatch.fnmatchcase(path.name, pattern) for pattern in NOT_MODULES
    )


def _stem(path: Path) -> str:
    """``number.test.ts`` -> ``number``; ``Text.module.css`` -> ``Text``."""
    return path.name.split(".")[0]


def _by_kind(kind: str) -> list[str]:
    return [d for d in WEB_DIRS if (_declaration(d) or {}).get("kind") == kind]


# ----------------------------------------------------------------------------- the registry


def test_web_declarations_are_well_formed_and_not_stale() -> None:
    assert (REPO_ROOT / WEB["doc"]).is_file(), WEB["doc"]
    paths = [d["path"] for d in DIRS]
    assert len(paths) == len(set(paths)), "duplicate [[web_dir]] paths"
    for decl in DIRS:
        assert decl["path"].startswith(WEB["root"]), decl["path"]
        assert decl.get("purpose"), f"{decl['path']}: needs a one-line purpose"
        assert decl.get("kind") in KINDS, decl
        # A glob (a slot such as features/*) may match nothing yet; an exact path must exist.
        if "*" not in decl["path"]:
            assert (REPO_ROOT / decl["path"]).is_dir(), (
                f"[[web_dir]] {decl['path']} does not exist: remove it from {LAYOUT_FILE}"
            )


def test_every_web_directory_is_declared() -> None:
    undeclared = [d for d in WEB_DIRS if _declaration(d) is None]
    assert not undeclared, f"undeclared web directories {undeclared}: {HINT}"


# ----------------------------------------------------------------------------- modules


def test_web_directories_hold_at_most_max_modules() -> None:
    limit = LAYOUT["max_modules"]
    over = {
        _rel(d): n for d in WEB_TREE if (n := sum(map(_is_module, _files(d)))) > limit
    }  # fmt: skip
    assert not over, f"more than {limit} modules (split the folder by kind; {GUIDE}): {over}"


def test_no_web_module_has_a_grab_bag_name() -> None:
    banned = LAYOUT["banned_module_names"]
    found = [
        _rel(f)
        for d in WEB_TREE
        for f in _files(d)
        if f.suffix in CODE_SUFFIXES and _stem(f).lower() in banned["names"]
    ]
    assert not found, f"grab-bag module names {found}: {banned['reason']} ({LAYOUT_FILE}; {GUIDE})"


def test_stylesheets_live_only_in_the_design_system() -> None:
    stray = [
        _rel(f)
        for d in WEB_TREE
        if not (_declaration(_rel(d)) or {}).get("styles")
        for f in _files(d)
        if f.suffix in STYLE_SUFFIXES
    ]
    assert not stray, (
        f"stylesheets outside the design system {stray}: styling lives only in "
        f"apps/web/design-system (CSS Modules + tokens); app code uses component props "
        f"(ADR 0025 rule 3; .claude/skills/add-ui-component)"
    )


# ----------------------------------------------------------------------------- kinds


@pytest.mark.parametrize("layer", _by_kind("layer"))
def test_layers_hold_only_folders(layer: str) -> None:
    # A design-system kind folder may re-export its components (index.ts); app layers may not.
    allowed = LAYER_FILES | ({"index.ts"} if "/design-system/" in layer else set())
    stray = [f.name for f in _files(REPO_ROOT / layer) if f.name not in allowed]
    assert not stray, (
        f"{layer} holds only slice folders (+ README.md); move {stray} into a declared slice "
        f"folder ({GUIDE})"
    )


@pytest.mark.parametrize("slice_dir", _by_kind("slice"))
def test_every_slice_has_a_public_index(slice_dir: str) -> None:
    assert (REPO_ROOT / slice_dir / "index.ts").is_file(), (
        f"{slice_dir}: add index.ts, the slice's public API; other slices import only it "
        f"(ADR 0025 rule 2; {GUIDE})"
    )


@pytest.mark.parametrize("segment", _by_kind("segment"))
def test_segments_are_named_for_their_kind(segment: str) -> None:
    name = PurePosixPath(segment).name
    assert name in WEB["segment_names"], (
        f"{segment}: a slice's inner folder is one of {WEB['segment_names']} ({GUIDE})"
    )


@pytest.mark.parametrize("component", _by_kind("component"))
def test_every_component_folder_is_complete(component: str) -> None:
    name = PurePosixPath(component).name
    required = [
        f"{name}.tsx",
        f"{name}.module.css",
        f"{name}.stories.tsx",
        f"{name}.test.tsx",
        "index.ts",
    ]
    missing = [f for f in required if not (REPO_ROOT / component / f).is_file()]
    if not (REPO_ROOT / component / "__screenshots__").is_dir():
        missing.append("__screenshots__/ (npm run visual:update)")
    assert not missing, (
        f"{component} is missing {missing}: every design-system component has its story, "
        "test and screenshots (ADR 0025 rule 6; .claude/skills/add-ui-component)"
    )


@pytest.mark.parametrize("shots", _by_kind("screenshots"))
def test_screenshot_folders_hold_only_png(shots: str) -> None:
    stray = [f.name for f in _files(REPO_ROOT / shots) if f.suffix != ".png"]
    assert not stray, f"{shots} holds screenshot baselines (.png) only: {stray}"
