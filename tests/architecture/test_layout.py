"""Fitness tests for the directory layout (ADR 0020, ``architecture/layout.toml``).

- every Python module under ``src/`` and ``apps/`` lives in a declared directory;
- at most ``max_modules`` modules per directory (``[[exception]]`` entries only shrink);
- every package has an ``__init__.py`` docstring saying what the folder holds;
- vendor folders: each contributes a source to the source registry, and only the registry
  imports it;
- task domains: a module is a registered task or a private helper, imported only within its
  domain folder or by the task registry (``[[shared]]`` lists the reasoned exceptions).
"""

import ast
import fnmatch
import tomllib
from collections import defaultdict
from pathlib import Path, PurePosixPath
from typing import Any

import pytest

from algotrade_ingestion.sources.framework.registry import SOURCES
from algotrade_ingestion.tasks.framework.registry import TASKS
from tests.conftest import REPO_ROOT

LAYOUT_FILE = "architecture/layout.toml"
LAYOUT: dict[str, Any] = tomllib.loads((REPO_ROOT / LAYOUT_FILE).read_text())
HINT = f"declare it in {LAYOUT_FILE} (see .claude/skills/add-responsibility)"
DIRS: list[dict[str, Any]] = LAYOUT["dir"]
EXCEPTIONS = {e["path"]: e for e in LAYOUT.get("exception", [])}
SHARED = {s["module"]: s for s in LAYOUT.get("shared", [])}
PACKAGE_ROOTS = ("src", "apps/ingestion", "apps/backtest")  # directories on sys.path


def _rel(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def _modules() -> list[Path]:
    return sorted(
        p
        for top in ("src", "apps")
        for p in (REPO_ROOT / top).rglob("*.py")
        if not {".venv", "node_modules", "__pycache__"} & set(p.parts)
    )


MODULES = _modules()
CODE_DIRS = sorted({_rel(p.parent) for p in MODULES})


def _matches(directory: str, pattern: str) -> bool:
    """``*`` matches exactly one path segment."""
    parts, wanted = PurePosixPath(directory).parts, PurePosixPath(pattern).parts
    return len(parts) == len(wanted) and all(map(fnmatch.fnmatchcase, parts, wanted))


def _declaration(directory: str) -> dict[str, Any] | None:
    """The most specific declaration matching ``directory`` (exact path beats a glob)."""
    found = [d for d in DIRS if _matches(directory, d["path"])]
    return min(found, key=lambda d: d["path"].count("*"), default=None)


def _dirs_of_kind(kind: str) -> list[str]:
    return [d for d in CODE_DIRS if (_declaration(d) or {}).get("kind") == kind]


def _module_name(path: Path) -> str:
    """Dotted import name of a module under ``src/`` or ``apps/<app>/``."""
    rel = _rel(path.with_suffix(""))
    for prefix in sorted(PACKAGE_ROOTS, key=len, reverse=True):
        if rel.startswith(prefix + "/"):
            dotted = rel[len(prefix) + 1 :].replace("/", ".")
            return dotted.removesuffix(".__init__")
    raise AssertionError(f"{rel}: not under a package root")


def _package_of(directory: str) -> str:
    return _module_name(REPO_ROOT / directory / "__init__.py")


def _imports(path: Path) -> set[str]:
    out: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            out |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            out.add(node.module)
            out |= {f"{node.module}.{a.name}" for a in node.names}
    return out


IMPORTS = {_rel(p): _imports(p) for p in MODULES}


def _importers(package: str) -> set[str]:
    """Modules (repo paths) that import ``package`` or anything inside it."""
    return {
        path
        for path, names in IMPORTS.items()
        if any(n == package or n.startswith(package + ".") for n in names)
    }


# ----------------------------------------------------------------------------- the registry


def test_layout_declarations_are_well_formed_and_not_stale() -> None:
    assert (REPO_ROOT / LAYOUT["doc"]).is_file(), LAYOUT["doc"]
    for key in ("source_registry", "task_registry"):
        assert (REPO_ROOT / LAYOUT[key]).is_file(), f"{key}: {LAYOUT[key]}"
    paths = [d["path"] for d in DIRS]
    assert len(paths) == len(set(paths)), "duplicate [[dir]] paths"
    for decl in DIRS:
        assert decl.get("purpose"), f"{decl['path']}: needs a one-line purpose"
        assert decl.get("kind") in (None, "vendor", "task-domain"), decl
        unused = not any(_matches(d, decl["path"]) for d in CODE_DIRS)
        assert not unused, f"{decl['path']} holds no Python code: remove it from {LAYOUT_FILE}"
    for entry in [*EXCEPTIONS.values(), *SHARED.values()]:
        assert entry.get("reason"), f"{entry}: needs a reason"


def test_every_module_lives_in_a_declared_directory() -> None:
    undeclared = sorted({_rel(p.parent) for p in MODULES if _declaration(_rel(p.parent)) is None})
    assert not undeclared, f"undeclared directories {undeclared}: {HINT}"


# ----------------------------------------------------------------------------- size


def _module_counts() -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for path in MODULES:
        if path.name != "__init__.py":
            counts[_rel(path.parent)] += 1
    return counts


def test_directories_hold_at_most_max_modules() -> None:
    limit = LAYOUT["max_modules"]
    over = {d: n for d, n in _module_counts().items() if n > limit and d not in EXCEPTIONS}
    assert not over, f"more than {limit} modules (split the folder by kind, {HINT}): {over}"


def test_layout_exceptions_only_shrink() -> None:
    counts, limit = _module_counts(), LAYOUT["max_modules"]
    for path, entry in EXCEPTIONS.items():
        assert entry.get("until"), f"{path}: an exception needs `until`"
        assert counts.get(path, 0) > limit, (
            f"{path} has {counts.get(path, 0)} modules (limit {limit}): "
            f"remove its [[exception]] from {LAYOUT_FILE}"
        )


# ----------------------------------------------------------------------------- packages


@pytest.mark.parametrize("directory", CODE_DIRS)
def test_every_package_has_a_docstring_saying_what_it_holds(directory: str) -> None:
    init = REPO_ROOT / directory / "__init__.py"
    assert init.is_file(), f"{directory}: add an __init__.py with a docstring"
    assert ast.get_docstring(ast.parse(init.read_text())), f"{_rel(init)}: add a docstring"


# ----------------------------------------------------------------------------- vendors


def test_there_are_vendor_folders() -> None:
    assert len(_dirs_of_kind("vendor")) >= 5


@pytest.mark.parametrize("vendor", _dirs_of_kind("vendor"))
def test_every_vendor_folder_contributes_a_registered_source(vendor: str) -> None:
    package = _package_of(vendor)
    built_here = [
        name
        for name, spec in SOURCES.items()
        if str(getattr(spec.build, "__module__", "")).startswith(package + ".")
    ]
    assert built_here, f"{vendor}: register at least one source in {LAYOUT['source_registry']}"


@pytest.mark.parametrize("vendor", _dirs_of_kind("vendor"))
def test_only_the_source_registry_imports_a_vendor_folder(vendor: str) -> None:
    outside = {p for p in _importers(_package_of(vendor)) if not p.startswith(vendor + "/")}
    stray = sorted(outside - {LAYOUT["source_registry"]})
    assert not stray, f"{vendor} is imported outside its folder (use the registry): {stray}"


# ----------------------------------------------------------------------------- task domains


def _registered_task_modules() -> set[str]:
    return {_rel(Path(str(t.module.__file__)).resolve()) for t in TASKS.values()}


@pytest.mark.parametrize("domain", _dirs_of_kind("task-domain"))
def test_task_domain_modules_stay_inside_their_domain(domain: str) -> None:
    allowed = {LAYOUT["task_registry"]}
    registered = _registered_task_modules()
    for path in sorted((REPO_ROOT / domain).glob("*.py")):
        rel = _rel(path)
        if path.name == "__init__.py":
            continue
        importers = _importers(_module_name(path)) - {rel}
        inside = {p for p in importers if p.startswith(domain + "/")}
        outside = importers - inside - allowed
        if rel in SHARED:
            assert outside, f"{rel} is no longer shared: remove it from [[shared]]"
            continue
        assert not outside, (
            f"{rel} is imported from outside {domain}: {sorted(outside)}. Move the code into the "
            f"domain, or list it in [[shared]] in {LAYOUT_FILE} with the reason"
        )
        assert rel in registered or inside, (
            f"{rel} is neither a registered task ({LAYOUT['task_registry']}) nor a helper "
            f"used inside {domain}"
        )


def test_shared_modules_are_task_domain_modules() -> None:
    domains = _dirs_of_kind("task-domain")
    for module in SHARED:
        assert (REPO_ROOT / module).is_file(), f"[[shared]] {module} does not exist"
        assert any(module.startswith(d + "/") for d in domains), module
