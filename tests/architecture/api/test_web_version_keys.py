"""The web page cache follows the generation an answer carries (ADR 0077 decision 18) through the
query key a hook hands to ``gql``: every ``gql`` call of an operation outside ``SHARED_OPERATIONS``
(its answers carry ``x-config-generation``) passes the key (a third argument; ``null`` outside a
query); a shared operation, which carries none, may leave it off. Without the key the operation's
name never joins the user-keyed set and a write from another tab leaves its queries fresh."""

import re
from pathlib import Path

from algotrade_api.graphql.response_cache import SHARED_OPERATIONS
from tests.conftest import REPO_ROOT

WEB_SRC = REPO_ROOT / "apps/web/src"
DOCUMENT = re.compile(r"\bconst\s+(\w+)\s*=\s*graphql\(\s*[`'\"]\s*query\s+(\w+)")
CALL = re.compile(r"(?<![\w.])gql\(")


def _arguments(source: str, start: int) -> int:
    """How many top-level arguments the call whose ``(`` ends at ``start`` has."""
    depth, count, index = 1, 1, start
    while depth:
        char = source[index]
        if char in "([{":
            depth += 1
        elif char in ")]}":
            depth -= 1
        elif char == "," and depth == 1 and source[index + 1 :].strip()[:1] not in ")":
            count += 1
        index += 1
    return count


def _sources() -> list[Path]:
    return [
        p
        for p in sorted(WEB_SRC.rglob("*.ts*"))
        if "generated" not in p.parts and ".test." not in p.name and p.name != "graphql.ts"
    ]


def test_every_gql_call_of_a_user_keyed_operation_passes_its_query_key() -> None:
    sources = {p: p.read_text() for p in _sources()}
    operations = {name: op for text in sources.values() for name, op in DOCUMENT.findall(text)}
    missing, seen = [], 0
    for path, text in sources.items():
        for call in CALL.finditer(text):
            name = re.match(r"\s*(\w+)", text[call.end() :])
            if name is None or name.group(1) not in operations:
                continue
            seen += 1
            operation = operations[name.group(1)]
            if operation not in SHARED_OPERATIONS and _arguments(text, call.end()) < 3:
                missing.append(f"{path.relative_to(REPO_ROOT)}: {operation}")
    assert seen > 40, "the parse found too few gql calls: the pattern drifted"
    assert not missing, (
        "pass the queryFn context's queryKey as gql's third argument (or null outside a "
        f"query): {missing}"
    )
