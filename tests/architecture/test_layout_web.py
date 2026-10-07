"""Fitness tests for the web app's directory layout (ADR 0025, ``[[web_dir]]`` in
``architecture/web_layout.toml``).

- every directory under ``apps/web`` (build output and ``node_modules`` skipped) is declared;
- at most ``max_modules`` modules per directory (``index.ts``, tests, stories and ``.d.ts``
  are not modules) and no grab-bag module names (``utils.ts``, ``helpers.ts``, ...);
- ``kind = "layer"`` folders hold only folders and a README; a ``slice`` has a public
  ``index.ts``; a ``segment`` is named for its kind; a ``component`` has its source, styles,
  story, test, index and screenshots; ``screenshots`` hold only ``.png``;
- stylesheets only where ``styles = true`` (the design system);
- no fact the server owns is derived in ``src/``
  (``architecture/web_forbidden_derivations.toml``, ADR 0038);
- no explanatory prose is added to ``src/``: explanations are Guide content shown through the
  help drawer, the older prose is a shrink-only baseline (``architecture/web_prose.toml``,
  ADR 0051).

Import rules between these folders are ESLint's (``apps/web/lint-rules/``); the per-story
completeness of design-system components is ``npm run ds:check``.
"""

import fnmatch
import re
import tomllib
from pathlib import Path, PurePosixPath
from typing import Any

import pytest

from tests.conftest import REPO_ROOT

LAYOUT_FILE = "architecture/layout.toml"  # shared settings: max_modules, banned_module_names
WEB_LAYOUT_FILE = "architecture/web_layout.toml"  # the [web] settings and every [[web_dir]]
LAYOUT: dict[str, Any] = tomllib.loads((REPO_ROOT / LAYOUT_FILE).read_text())
WEB_LAYOUT: dict[str, Any] = tomllib.loads((REPO_ROOT / WEB_LAYOUT_FILE).read_text())
WEB: dict[str, Any] = WEB_LAYOUT["web"]
DIRS: list[dict[str, Any]] = WEB_LAYOUT["web_dir"]
GUIDE = "docs/ui/architecture.md (where it goes) and .claude/skills/add-web-page"
HINT = f"declare it as a [[web_dir]] in {WEB_LAYOUT_FILE} with a purpose; see {GUIDE}"
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
                f"[[web_dir]] {decl['path']} does not exist: remove it from {WEB_LAYOUT_FILE}"
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


# ----------------------------------------------------------------------------- derived facts

DERIVATIONS_FILE = "architecture/web_forbidden_derivations.toml"
DERIVED_SKIP = ("*.test.*", "*.spec.*", "*.stories.*", "*.d.ts")


def forbidden_derivations(src: Path, patterns: list[dict[str, Any]]) -> list[str]:
    """``file:line: reason`` for each line of ``src/**/*.{ts,tsx}`` (tests, stories and
    generated files left out) matching a pattern outside its ``allowed`` path prefixes."""
    compiled = [(re.compile(p["regex"]), p) for p in patterns]
    found = []
    for path in sorted(src.rglob("*.ts*")):
        rel = path.relative_to(src.parent).as_posix()
        if path.suffix not in (".ts", ".tsx") or "/generated/" in rel:
            continue
        if any(fnmatch.fnmatchcase(path.name, skip) for skip in DERIVED_SKIP):
            continue
        for n, line in enumerate(path.read_text().splitlines(), start=1):
            for regex, pattern in compiled:
                if regex.search(line) and not rel.startswith(tuple(pattern.get("allowed", []))):
                    found.append(f"{rel}:{n}: {pattern['reason']}")
    return found


def test_no_forbidden_derivations() -> None:
    """ADR 0038: the browser renders facts the server sends, it never derives them."""
    patterns = tomllib.loads((REPO_ROOT / DERIVATIONS_FILE).read_text()).get("pattern", [])
    assert patterns, f"{DERIVATIONS_FILE} has no enabled pattern"
    found = forbidden_derivations(REPO_ROOT / WEB["root"] / "src", patterns)
    assert not found, (
        f"facts derived in the browser ({DERIVATIONS_FILE}; docs/api/read-model.md):\n"
        + "\n".join(found)
    )


def test_forbidden_derivations_respect_allowed_paths(tmp_path: Path) -> None:
    src = tmp_path / "src"
    (src / "shared" / "lib").mkdir(parents=True)
    (src / "widgets").mkdir()
    (src / "shared" / "lib" / "clock.ts").write_text("const now = new Date();\n")
    (src / "widgets" / "w.tsx").write_text("ok\nconst t = new Date();\n")
    (src / "widgets" / "w.test.tsx").write_text("const t = new Date();\n")
    patterns = [{"regex": r"new Date\(\)", "reason": "ask", "allowed": ["src/shared/lib/"]}]
    assert forbidden_derivations(src, patterns) == ["src/widgets/w.tsx:2: ask"]


PROSE_FILE = "architecture/web_prose.toml"
PROSE_HINT = (
    "an explanation is a Guide entry shown through the help drawer (ADR 0051; "
    ".claude/skills/add-guide-content); microcopy is one sentence under 25 words"
)
_COMMENT = re.compile(r"/\*.*?\*/|(?<![:\"'])//[^\n]*", re.S)
_JSX_TEXT = re.compile(r">([^<>{}]+)<")
_STRING = re.compile(r"'((?:[^'\\\n]|\\.)*)'|\"((?:[^\"\\\n]|\\.)*)\"|`((?:[^`\\]|\\.)*)`")
_CODE = re.compile(r"=|&&|\|\||\n|\b(?:const|return|function)\b")
_WORD = re.compile(r"[A-Za-z][A-Za-z\u2019'-]*")
_SENTENCE_END = re.compile(r"[.!?](?=\s+[A-Z(]|\s*$)")
_EXPLAINER = re.compile(
    r"<Disclosure\b[^>]*?label=[\"'{`]+[^\"'}`]*?(?:how to read|why it matters|learn more|what is)",
    re.I | re.S,
)


def _is_prose(text: str, settings: dict[str, Any]) -> bool:
    words = len(_WORD.findall(text))
    sentences = len(_SENTENCE_END.findall(text))
    return words >= settings["min_words"] and (
        sentences >= 2 or words >= settings["max_sentence_words"]
    )


def prose_findings(text: str, settings: dict[str, Any]) -> list[str]:
    """The explanatory prose and explainer Disclosures in one TS / TSX source (comments,
    code between tags and multi-line template literals such as GraphQL documents left out)."""
    text = _COMMENT.sub("", text)
    found = []
    for match in _JSX_TEXT.finditer(text):
        jsx = " ".join(match.group(1).split())
        if not _CODE.search(jsx) and _is_prose(jsx, settings):
            found.append(jsx)
    for match in _STRING.finditer(text):
        literal = next(group for group in match.groups() if group is not None)
        if not _CODE.search(literal) and _is_prose(re.sub(r"\$\{[^}]*\}", "X", literal), settings):
            found.append(literal)
    found += [match.group(0) for match in _EXPLAINER.finditer(text)]
    return found


def prose_counts(src: Path, settings: dict[str, Any]) -> dict[str, int]:
    """Findings per file of ``src/**/*.{ts,tsx}`` (tests, stories, generated left out), keyed
    by the path relative to ``src``'s parent (``apps/web``)."""
    counts = {}
    for path in sorted(src.rglob("*.ts*")):
        rel = path.relative_to(src.parent).as_posix()
        if path.suffix not in (".ts", ".tsx") or "/generated/" in rel:
            continue
        if any(fnmatch.fnmatchcase(path.name, skip) for skip in DERIVED_SKIP):
            continue
        if found := prose_findings(path.read_text(), settings):
            counts[rel] = len(found)
    return counts


def test_web_prose_matches_the_baseline() -> None:
    """ADR 0051: explanations live in the Guide; the baseline of older prose only shrinks."""
    settings = tomllib.loads((REPO_ROOT / PROSE_FILE).read_text())
    baseline: dict[str, int] = settings["baseline"]
    counts = prose_counts(REPO_ROOT / WEB["root"] / "src", settings)
    over = [
        f"{rel}: {n} (baseline {baseline.get(rel, 0)})"
        for rel, n in counts.items()
        if n > baseline.get(rel, 0)
    ]
    assert not over, f"explanatory prose in the web code; {PROSE_HINT}:\n" + "\n".join(over)
    under = [
        f"{rel}: {counts.get(rel, 0)} (baseline {n})"
        for rel, n in baseline.items()
        if counts.get(rel, 0) < n
    ]
    assert not under, f"prose removed: lower or delete these lines of {PROSE_FILE}:\n" + "\n".join(
        under
    )


def test_prose_findings_tell_explanations_from_microcopy() -> None:
    settings = {"min_words": 12, "max_sentence_words": 25}
    source = """
    // A comment of many words that explains a lot of things to the reader of the code.
    const q = `
      query Long { one two three four five six seven eight nine ten eleven twelve }`;
    <Text>No screener yet.</Text>
    <Text>Ranked by your screener priority, then score. Reorder the screeners to change it.</Text>
    <Text>{a > b ? 'x' : 'y'} and some words that read like code const x = 1 here then</Text>
    const hint = "Plain English: the rows are a draft. Review each one before you save it here.";
    <Disclosure label="How to read it">
    <Disclosure label="Missing data">
    """
    assert prose_findings(source, settings) == [
        "Ranked by your screener priority, then score. Reorder the screeners to change it.",
        "Plain English: the rows are a draft. Review each one before you save it here.",
        '<Disclosure label="How to read',
    ]
