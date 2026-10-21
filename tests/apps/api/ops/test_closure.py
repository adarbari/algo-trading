"""The API's static import closure (ADR 0077 decision 21 item 5, ADR 0079): which changed
paths are code the API process loads, and a fitness test that it covers what really loads."""

import subprocess
import sys

from algotrade_api.ops.closure import DiskTree, GitTree, api_loads, loaded_paths
from algotrade_api.ops.deploy import Action, actions
from tests.conftest import REPO_ROOT

R = Action.RESTART

API_INIT = "apps/api/algotrade_api/__init__.py"


def _tree(tmp_path, files: dict[str, str]) -> DiskTree:
    base = {
        API_INIT: "",
        "apps/api/algotrade_api/main.py": "from algotrade.services import read\n",
        "src/algotrade/__init__.py": "",
        "src/algotrade/services/__init__.py": "",
        "src/algotrade/services/read.py": "",
        "src/algotrade/features/__init__.py": "",
        "src/algotrade/features/ingest_only.py": "x = 1\n",
    }
    base.update(files)
    for rel, text in base.items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    return DiskTree(tmp_path)


def test_an_ingestion_only_src_module_does_not_restart(tmp_path) -> None:
    tree = _tree(tmp_path, {})
    assert actions(["src/algotrade/features/ingest_only.py"], tree) == []


def test_an_api_loaded_module_restarts(tmp_path) -> None:
    tree = _tree(tmp_path, {})
    assert actions(["src/algotrade/services/read.py"], tree) == [R]
    assert actions(["src/algotrade/services/__init__.py"], tree) == [R]


def test_a_module_imported_lazily_inside_a_function_restarts(tmp_path) -> None:
    tree = _tree(
        tmp_path,
        {
            "apps/api/algotrade_api/routes.py": (
                "def f():\n    from algotrade.features import ingest_only\n"
            ),
        },
    )
    assert actions(["src/algotrade/features/ingest_only.py"], tree) == [R]


def test_a_relative_import_and_a_from_import_of_a_submodule_restart(tmp_path) -> None:
    tree = _tree(
        tmp_path,
        {
            "src/algotrade/services/read.py": (
                "from . import sub\nfrom ..features import ingest_only\n"
            ),
            "src/algotrade/services/sub.py": "",
        },
    )
    assert actions(["src/algotrade/services/sub.py"], tree) == [R]
    assert actions(["src/algotrade/features/ingest_only.py"], tree) == [R]


def test_a_package_that_loads_dynamically_is_wholly_loaded(tmp_path) -> None:
    tree = _tree(
        tmp_path,
        {
            "src/algotrade/services/__init__.py": (
                "import pkgutil\nfor m in pkgutil.iter_modules(__path__):\n    pass\n"
            ),
            "src/algotrade/services/hidden.py": "from algotrade.features import ingest_only\n",
        },
    )
    assert actions(["src/algotrade/services/hidden.py"], tree) == [R]
    # what a wholly loaded package imports is loaded too
    assert actions(["src/algotrade/features/ingest_only.py"], tree) == [R]


def test_dunder_import_and_import_module_are_dynamic_loading(tmp_path) -> None:
    for call in ("__import__('x')", "importlib.import_module('x')", "entry_points()"):
        tree = _tree(tmp_path, {"src/algotrade/services/read.py": f"\n{call}\n"})
        assert api_loads("src/algotrade/services/read.py", tree)
        assert api_loads("src/algotrade/services/sibling.py", tree)  # unreadable: deny


def test_a_mention_in_a_docstring_is_not_dynamic_loading(tmp_path) -> None:
    tree = _tree(tmp_path, {"src/algotrade/services/read.py": '"""Not __import__ at all."""\n'})
    assert not api_loads("src/algotrade/features/ingest_only.py", tree)


def test_anything_unclassifiable_restarts(tmp_path) -> None:
    tree = _tree(
        tmp_path, {"src/algotrade/data.toml": "", "src/algotrade/features/data.json": "{}"}
    )
    assert actions(["src/algotrade/data.toml"], tree) == [R]  # package data
    assert actions(["src/algotrade/features/data.json"], tree) == [R]
    assert actions(["config/site/sources.toml"], tree) == [R]
    assert actions(["apps/api/algotrade_api/anything.txt"], tree) == [R]
    assert actions(["src/algotrade/gone.py"], tree) == [R]  # not in the target tree
    assert actions(["src/stray.py"], tree) == [R]  # not in a package
    assert actions(["uv.lock"], tree) == [Action.SYNC, R]


def test_an_api_module_always_restarts_and_the_rest_never_does(tmp_path) -> None:
    tree = _tree(tmp_path, {"apps/api/algotrade_api/orphan.py": ""})
    assert actions(["apps/api/algotrade_api/orphan.py"], tree) == [R]
    assert actions(["apps/ingestion/algotrade_ingestion/x.py", "apps/backtest/x.py"], tree) == []
    assert actions(["tests/unit/x.py", "docs/a.md"], tree) == []


def test_a_git_tree_reads_the_commit_not_the_working_directory(tmp_path) -> None:
    def git(*args: str) -> None:
        subprocess.run(["git", *args], cwd=tmp_path, check=True, capture_output=True)

    git("init", "-q")
    git("config", "user.email", "t@t")
    git("config", "user.name", "t")
    _tree(tmp_path, {})
    git("add", ".")
    git("commit", "-qm", "c")
    (tmp_path / "apps/api/algotrade_api/main.py").write_text("")  # uncommitted: not seen
    assert actions(["src/algotrade/services/read.py"], GitTree("HEAD", tmp_path)) == [R]
    assert actions(["src/algotrade/features/ingest_only.py"], GitTree("HEAD", tmp_path)) == []


def test_the_static_closure_covers_every_module_the_api_loads_at_runtime() -> None:
    """Fitness: drift between the static closure and what the process imports would leave a
    stale API after a deploy that skipped the restart."""
    code = (
        "import sys, algotrade_api.main\n"
        "print('\\n'.join(m for m in sys.modules if m.startswith('algotrade')))"
    )
    done = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True, cwd=REPO_ROOT
    )
    runtime = {m for m in done.stdout.split() if m}
    assert runtime, "the API imported nothing from algotrade*"
    static = loaded_paths(DiskTree(REPO_ROOT))
    missing = sorted(m for m in runtime if not _module_path_in(m, static))
    assert not missing, f"loaded at runtime but missing from the static closure: {missing}"


def _module_path_in(module: str, paths: frozenset[str]) -> bool:
    rel = module.replace(".", "/")
    for root in ("src", "libs/sources", "apps/api"):
        if f"{root}/{rel}.py" in paths or f"{root}/{rel}/__init__.py" in paths:
            return True
    return False
