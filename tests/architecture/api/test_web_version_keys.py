"""The web page cache follows the generation an answer carries (ADR 0077 decision 18) through the
query key a hook hands to ``gql``: every ``gql`` call of an operation outside ``SHARED_OPERATIONS``
(its answers carry ``x-config-generation``) passes the key (a third argument; ``null`` outside a
query); a shared operation, which carries none, may leave it off. Without the key the operation's
name never joins the user-keyed set and a write from another tab leaves its queries fresh."""

import re
from pathlib import Path

from algotrade_api.graphql.response_cache import RUN_OPERATIONS, SHARED_OPERATIONS
from tests.conftest import REPO_ROOT

WEB_SRC = REPO_ROOT / "apps/web/src"
# a document is `graphql(`query Name ...`)` or `new TypedDocumentString<...>(`query Name ...`)`
DOCUMENT = re.compile(
    r"\bconst\s+(\w+)\s*=\s*(?:graphql\(|new\s+TypedDocumentString\b[^`'\"]*?\()"
    r"\s*[`'\"]\s*query\s+(\w+)"
)
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
    # a const name repeats across files (`Document`): the file's own first, then the imported
    everywhere = {name: op for text in sources.values() for name, op in DOCUMENT.findall(text)}
    missing, seen = [], 0
    for path, text in sources.items():
        operations = everywhere | dict(DOCUMENT.findall(text))
        for call in CALL.finditer(text):
            name = re.match(r"\s*(\w+)", text[call.end() :])
            if name is None or name.group(1) not in operations:
                continue
            seen += 1
            operation = operations[name.group(1)]
            if operation not in SHARED_OPERATIONS and _arguments(text, call.end()) < 3:
                missing.append(f"{path.relative_to(REPO_ROOT)}: {operation}")
    assert seen > 70, "the parse found too few gql calls: the pattern drifted"
    assert "EdgeCompare" in everywhere.values(), "a TypedDocumentString document is not parsed"
    assert not missing, (
        "pass the queryFn context's queryKey as gql's third argument (or null outside a "
        f"query): {missing}"
    )


# ``Session.dataStatus`` depends on the viewer's screeners and on run records, so a web operation
# that selects it is a ``RUN_OPERATIONS`` entry (user-keyed, runs generation in the key), never a
# ``SHARED_OPERATIONS`` one (role-keyed: a trader would read another viewer's counts).
STATUS_DOCUMENT = re.compile(r"query\s+(\w+)[^`'\"]*", re.S)


def _selecting(text: str) -> list[str]:
    """The names of the queries in ``text`` whose document selects ``dataStatus``."""
    return [m.group(1) for m in STATUS_DOCUMENT.finditer(text) if "dataStatus" in m.group(0)]


def test_the_parse_finds_a_query_that_selects_the_field() -> None:
    sample = "const D = graphql(`\n query Pill { session { dataStatus { state } } }\n`)"
    assert _selecting(sample) == ["Pill"]


def test_an_operation_selecting_data_status_is_a_run_operation() -> None:
    found = {
        name
        for path in sorted(WEB_SRC.rglob("*.ts*"))
        if "generated" not in path.parts
        for name in _selecting(path.read_text())
    }
    wrong = sorted(n for n in found if n not in RUN_OPERATIONS or n in SHARED_OPERATIONS)
    assert not wrong, f"add to RUN_OPERATIONS (response_cache.py), not SHARED_OPERATIONS: {wrong}"
