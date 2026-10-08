"""Every call to the text model says who asks (ADR 0041, amended 2026-10-08): a ``.complete(``
call in ``src`` or ``apps`` without ``tag=`` would be answered as no user, so the owner's own
login would silently never serve the owner (and a new use case could not be told from another)."""

import ast
from pathlib import Path

from tests.conftest import REPO_ROOT

ROOTS = ("src", "apps")


def untagged() -> list[str]:
    found: list[str] = []
    for root in ROOTS:
        for path in sorted((REPO_ROOT / root).rglob("*.py")):
            if "node_modules" in path.parts:
                continue
            for node in ast.walk(ast.parse(path.read_text())):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "complete"
                    and not any(k.arg == "tag" for k in node.keywords)
                ):
                    found.append(f"{Path(path).relative_to(REPO_ROOT)}:{node.lineno}")
    return found


def test_every_text_model_call_passes_tag() -> None:
    assert untagged() == [], "pass tag=CallTag(use_case, user) to every TextModel.complete call"
