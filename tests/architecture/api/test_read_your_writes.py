"""The read-your-writes gate (ADR 0077 decisions 14-17): every write route the API serves is
listed in ``architecture/read_your_writes.toml`` with the test that proves its write shows on the
next read, or with the reason it persists nothing; the exempt list only shrinks."""

import ast
import subprocess
import tomllib
from pathlib import Path

from algotrade_api.deps import ApiSettings
from algotrade_api.main import create_app
from tests.conftest import REPO_ROOT
from tests.helpers.api_store import as_user

GATE = "architecture/read_your_writes.toml"
WRITES = ("put", "post", "patch", "delete")


def _served_write_routes(web_dist: Path) -> set[tuple[str, str]]:
    """(METHOD, path) of every write route in the OpenAPI document except ``POST /graphql``."""
    (web_dist / "index.html").write_text("<!doctype html>")
    settings = ApiSettings("memory://", "config", web_dist=web_dist)
    paths = create_app(settings, authenticator=as_user()).openapi()["paths"]
    return {
        (method.upper(), path)
        for path, ops in paths.items()
        for method in ops
        if method in WRITES and (method, path) != ("post", "/graphql")
    }


def _gate() -> dict:  # type: ignore[type-arg]
    return tomllib.loads((REPO_ROOT / GATE).read_text())


def test_every_write_route_is_listed_and_every_entry_is_served(tmp_path: Path) -> None:
    listed = {(r["method"], r["path"]) for r in _gate()["route"]}
    served = _served_write_routes(tmp_path)
    new, gone = sorted(served - listed), sorted(listed - served)
    assert not new, (
        f"write routes not in {GATE}: {new}. A route that persists something needs a test in "
        "tests/contract/api/read_your_writes/ that writes through it and reads the change back "
        "through the cached GraphQL operation; a dry run needs an `exempt` reason"
    )
    assert not gone, f"{GATE} lists routes the API no longer serves: {gone}"
    assert len(listed) == len(_gate()["route"]), "a route is listed twice"


def _functions(path: Path) -> set[str]:
    return {
        node.name
        for node in ast.walk(ast.parse(path.read_text()))
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
    }


def test_each_route_has_a_resolvable_test_or_a_reason() -> None:
    problems = []
    for route in _gate()["route"]:
        name = f"{route['method']} {route['path']}"
        test, exempt = route.get("test"), route.get("exempt")
        if (test is None) == (exempt is None):
            problems.append(f"{name}: exactly one of `test` and `exempt`")
        elif exempt is not None and not exempt.strip():
            problems.append(f"{name}: an empty exempt reason")
        elif test is not None:
            file, _, function = test.partition("::")
            path = REPO_ROOT / file
            if not path.is_file() or not function.startswith("test_"):
                problems.append(f"{name}: {test} is not a test in an existing file")
            elif function not in _functions(path):
                problems.append(f"{name}: no function {function} in {file}")
    assert not problems, f"{GATE}: {problems}"


def test_the_exempt_list_only_shrinks() -> None:
    gate = _gate()
    exempt = [r for r in gate["route"] if "exempt" in r]
    committed = subprocess.run(
        ["git", "show", f"origin/main:{GATE}"],
        cwd=REPO_ROOT, capture_output=True, text=True, check=False,
    )  # fmt: skip
    if committed.returncode == 0:  # absent before the gate's first merge: nothing to compare
        before = tomllib.loads(committed.stdout)["max_exempt"]
        assert gate["max_exempt"] <= before, (
            f"max_exempt rose from {before} to {gate['max_exempt']}: the exempt list only shrinks"
        )
    assert len(exempt) == gate["max_exempt"], (
        f"{len(exempt)} exempt routes but max_exempt = {gate['max_exempt']}: a new exemption is "
        "not allowed (write the test); after removing one, lower max_exempt"
    )


def test_one_test_function_proves_one_route() -> None:
    tests = [r["test"] for r in _gate()["route"] if "test" in r]
    assert len(tests) == len(set(tests)), "a test function is listed for two routes"
