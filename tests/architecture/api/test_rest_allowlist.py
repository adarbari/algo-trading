"""The REST GET allow-list (ADR 0037, READ 5): every GET route the API serves is listed in
``architecture/rest_allowlist.toml``, no route hides from the OpenAPI document, and the list
only shrinks (page reads move to GraphQL, docs/api/read-model.md "What stays REST")."""

import subprocess
import sys
import tomllib

from algotrade_api.deps import ApiSettings
from algotrade_api.main import create_app
from tests.conftest import REPO_ROOT

REST_ALLOWLIST = "architecture/rest_allowlist.toml"


def _served_get_routes() -> set[str]:
    """Every GET path the API serves, from its OpenAPI document (the app as served)."""
    paths = create_app(ApiSettings("memory://", "config")).openapi()["paths"]
    return {path for path, ops in paths.items() if "get" in ops}


def test_rest_get_routes_are_allowlisted() -> None:
    listed = {r["path"] for r in tomllib.loads((REPO_ROOT / REST_ALLOWLIST).read_text())["route"]}
    served = _served_get_routes()
    new, gone = sorted(served - listed), sorted(listed - served)
    assert not new, (
        f"GET routes not in {REST_ALLOWLIST}: {new}. A read for a page is a GraphQL field "
        "(.claude/skills/add-graphql-field), not a REST GET; any other GET needs an ADR 0037 "
        "amendment and an entry with keep = true and its reason"
    )
    assert not gone, (
        f"{REST_ALLOWLIST} lists routes the API no longer serves: {gone}. Remove them, then "
        "`make rest-allowlist-update` lowers the committed count"
    )


def test_no_route_hides_from_the_openapi_document() -> None:
    """The allow-list check reads the OpenAPI document, so every route must be in it."""
    hidden = [
        p.relative_to(REPO_ROOT).as_posix()
        for p in (REPO_ROOT / "apps" / "api").rglob("*.py")
        if "include_in_schema" in p.read_text()
    ]
    assert not hidden, f"routes hidden from OpenAPI escape the REST allow-list: {hidden}"


def test_rest_allowlist_only_shrinks() -> None:
    proc = subprocess.run(
        [sys.executable, "scripts/check_rest_allowlist.py"],
        cwd=REPO_ROOT, capture_output=True, text=True, check=False,
    )  # fmt: skip
    assert proc.returncode == 0, proc.stdout + proc.stderr
