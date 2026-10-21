"""Which changed paths are code the API process loads (ADR 0077 decision 21 item 5, ADR 0079):
the static import closure of the API, computed by AST from one tree of the repo.

A deploy restarts the API (cold caches, minutes of slow pages) only when a changed path is in
that closure. Every doubt restarts: a path that is not a ``.py`` module of a package (data,
config, anything unclassifiable), a module missing from the target tree, a module the closure
cannot read. The closure includes imports inside functions and under ``TYPE_CHECKING``; a loaded
module that loads others dynamically (``__import__``, ``importlib``, ``pkgutil`` walks, entry
points) makes its whole package loaded. Every module of ``algotrade_api`` is a root: the API's
own code is the API (``cli`` is what launchd runs, ``main`` what serves).
"""

import ast
import contextlib
import os
import subprocess
from collections.abc import Iterator
from pathlib import Path
from typing import Protocol

# The directories under which code the API's process could load lives (``libs/<lib>`` holds
# the packages of one library).
_BASES = ("src", "apps/api", "libs")
_API_PACKAGE = "algotrade_api"
_SKIP_DIRS = frozenset({"__pycache__", "node_modules", ".venv", ".git", "dist", "build"})
# Names whose mere mention means a module may load code the AST cannot see.
_DYNAMIC = frozenset(
    {"__import__", "import_module", "iter_modules", "walk_packages", "entry_points",
     "find_spec", "run_module", "load_module"}
)  # fmt: skip


class Tree(Protocol):
    """A tree of the repo at one commit (or on disk): its files and their text."""

    def files(self) -> frozenset[str]:
        """Repo-relative paths under the code roots (every file, not only ``.py``)."""
        ...

    def read(self, path: str) -> str | None:
        """The text of ``path``, ``None`` when absent or unreadable."""
        ...


class DiskTree:
    """The working tree under ``root``."""

    def __init__(self, root: Path) -> None:
        self._root = root

    def files(self) -> frozenset[str]:
        out: set[str] = set()
        for base in _BASES:
            for dirpath, dirs, names in os.walk(self._root / base):
                dirs[:] = [d for d in dirs if d not in _SKIP_DIRS]
                out.update((Path(dirpath) / n).relative_to(self._root).as_posix() for n in names)
        return frozenset(out)

    def read(self, path: str) -> str | None:
        try:
            return (self._root / path).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return None


class GitTree:
    """The files of commit ``rev`` of the repository in ``cwd`` (not the working directory:
    the plan runs from a checkout that is not at the target)."""

    def __init__(self, rev: str, cwd: Path | None = None) -> None:
        self._rev = rev
        self._cwd = cwd
        self._texts: dict[str, str] | None = None

    def _git(self, *args: str) -> str:
        done = subprocess.run(
            ["git", *args], cwd=self._cwd, capture_output=True, text=True, check=True
        )
        return done.stdout

    def files(self) -> frozenset[str]:
        names = self._git("ls-tree", "-r", "--name-only", "-z", self._rev, "--", *_BASES)
        return frozenset(n for n in names.split("\0") if n)

    def read(self, path: str) -> str | None:
        if self._texts is None:  # one ``git cat-file --batch`` for every .py file
            self._texts = self._read_all()
        return self._texts.get(path)

    def _read_all(self) -> dict[str, str]:
        names = sorted(f for f in self.files() if f.endswith(".py"))
        request = "".join(f"{self._rev}:{n}\n" for n in names).encode()
        done = subprocess.run(
            ["git", "cat-file", "--batch"],
            cwd=self._cwd, input=request, capture_output=True, check=True,
        )  # fmt: skip
        out: dict[str, str] = {}
        data, pos = done.stdout, 0
        for name in names:
            end = data.index(b"\n", pos)
            header = data[pos:end].split()
            if len(header) != 3:  # "<spec> missing": left out, read as unreadable
                pos = end + 1
                continue
            size = int(header[2])
            body = data[end + 1 : end + 1 + size]
            pos = end + 1 + size + 1
            with contextlib.suppress(UnicodeDecodeError):
                out[name] = body.decode("utf-8")
        return out


def _module_of(path: str) -> tuple[str, str] | None:
    """``(module, base)`` of a ``.py`` path under a code root, ``None`` when it is none."""
    parts = path.split("/")
    if not path.endswith(".py"):
        return None
    if parts[0] == "libs":
        depth = 2  # libs/<lib>/<package>/...
    elif parts[0] == "src" or parts[:2] == ["apps", "api"]:
        depth = 1 if parts[0] == "src" else 2
    else:
        return None
    base, rest = "/".join(parts[:depth]), parts[depth:]
    if not rest:
        return None
    rest[-1] = rest[-1][:-3]
    if rest[-1] == "__init__":
        rest = rest[:-1]
    return (".".join(rest), base) if rest else None


def _dynamic(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id in _DYNAMIC:
            return True
        if isinstance(node, ast.Attribute) and node.attr in _DYNAMIC:
            return True
        if isinstance(node, ast.ImportFrom) and any(a.name in _DYNAMIC for a in node.names):
            return True
    return False


def _imports(tree: ast.AST, module: str, is_package: bool) -> Iterator[str]:
    package = module if is_package else module.rpartition(".")[0]
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                up = package.split(".") if package else []
                up = up[: len(up) - (node.level - 1)] if node.level > 1 else up
                base = ".".join([*up, *([node.module] if node.module else [])])
            else:
                base = node.module or ""
            if base:
                yield base
            for alias in node.names:  # ``from pkg import sub`` may name a submodule
                yield f"{base}.{alias.name}" if base else alias.name


def _modules(files: frozenset[str]) -> dict[str, str]:
    """module name -> path, for the ``.py`` files of packages (a top directory with an
    ``__init__.py``)."""
    out: dict[str, str] = {}
    for path in files:
        found = _module_of(path)
        if found is None:
            continue
        module, base = found
        top = f"{base}/{module.split('.')[0]}/__init__.py"
        if top in files:
            out[module] = path
    return out


def loaded_paths(tree: Tree) -> frozenset[str]:
    """The ``.py`` paths the API process may load: its own modules and everything they import,
    transitively, a dynamically loading module taking its whole package with it."""
    modules = _modules(tree.files())
    todo = [m for m in modules if m.split(".")[0] == _API_PACKAGE]
    loaded: set[str] = set()
    while todo:
        name = todo.pop()
        if name in loaded or name not in modules:
            continue
        loaded.add(name)
        path = modules[name]
        text = tree.read(path)
        try:
            parsed = ast.parse(text) if text is not None else None
        except SyntaxError:
            parsed = None
        is_package = path.endswith("/__init__.py")
        if parsed is None:  # cannot read it: take its whole package
            todo.extend(_below(modules, name if is_package else name.rpartition(".")[0]))
            continue
        if _dynamic(parsed):
            todo.extend(_below(modules, name if is_package else name.rpartition(".")[0]))
        for target in _imports(parsed, name, is_package):
            parts = target.split(".")  # importing a.b.c loads a, a.b and a.b.c
            todo.extend(".".join(parts[: i + 1]) for i in range(len(parts)))
    return frozenset(modules[m] for m in loaded)


def _below(modules: dict[str, str], package: str) -> list[str]:
    if not package:
        return []
    return [m for m in modules if m == package or m.startswith(package + ".")]


class ApiClosure:
    """What the API loads from one ``tree``, computed on first use."""

    def __init__(self, tree: Tree) -> None:
        self._tree = tree
        self._plan: tuple[frozenset[str], frozenset[str]] | None = None

    def loads(self, path: str) -> bool:
        """Whether changing ``path`` must restart the API. ``True`` unless ``path`` is a ``.py``
        module of a package present in the tree that the API's closure does not reach."""
        if self._plan is None:
            self._plan = (self._tree.files(), loaded_paths(self._tree))
        files, closure = self._plan
        return path in closure or path not in files or not _is_module(path, files)


def api_loads(path: str, tree: Tree) -> bool:
    """``ApiClosure(tree).loads(path)`` for one path."""
    return ApiClosure(tree).loads(path)


def _is_module(path: str, files: frozenset[str]) -> bool:
    found = _module_of(path)
    return found is not None and f"{found[1]}/{found[0].split('.')[0]}/__init__.py" in files
