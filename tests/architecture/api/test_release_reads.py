"""The serving release's read path (ADR 0077 decision 23): no loader keys on the live commit
sequence, and the operations answered from the release are exactly the ones
``architecture/release_shared_ops.toml`` lists, each a SHARED operation with a reason and a test."""

import ast
import tomllib

from algotrade_api.graphql.response_cache import (
    RELEASE_FIELDS,
    RELEASE_SHARED_OPERATIONS,
    SHARED_OPERATIONS,
)
from tests.conftest import REPO_ROOT
from tests.helpers.api_store import field_paths, web_documents

LISTED = "architecture/release_shared_ops.toml"
BUILD = "src/algotrade/services/serving/build.py"


def test_no_cache_key_under_services_or_data_uses_the_live_sequence() -> None:
    """A cache key holds ``reader.version()``: ``("pin", X)`` for a release read, ``("live",
    seq)`` otherwise. A ``visible_seq()`` call would stay live under a pin (and a pinned and a
    live reader at the same sequence would share one entry). The one legitimate call takes the
    build's X (``services/serving/build.py``)."""
    found = []
    for tree in ("services", "data"):
        for path in sorted((REPO_ROOT / "src/algotrade" / tree).rglob("*.py")):
            if path.relative_to(REPO_ROOT).as_posix() == BUILD:
                continue
            for node in ast.walk(ast.parse(path.read_text())):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "visible_seq"
                ):
                    found.append(f"{path.relative_to(REPO_ROOT)}:{node.lineno}")
    assert not found, (
        f"visible_seq() calls under services/ or data/: {found}. Key on reader.version() "
        "(StoreReader.version: a pinned reader's key does not move with a commit)"
    )


def test_the_listed_operations_are_exactly_the_release_shared_operations() -> None:
    listed = tomllib.loads((REPO_ROOT / LISTED).read_text())["operation"]
    names = [o["name"] for o in listed]
    assert len(names) == len(set(names)), "an operation is listed twice"
    assert set(names) == RELEASE_SHARED_OPERATIONS, (
        f"{LISTED} and RELEASE_SHARED_OPERATIONS differ: "
        f"{sorted(set(names) ^ RELEASE_SHARED_OPERATIONS)}"
    )
    assert RELEASE_SHARED_OPERATIONS <= SHARED_OPERATIONS, "a release operation is role-only"


def test_every_listed_operation_has_a_reason_and_a_test_that_names_it() -> None:
    for entry in tomllib.loads((REPO_ROOT / LISTED).read_text())["operation"]:
        assert entry["reason"].strip(), f"{entry['name']}: no reason"
        test = REPO_ROOT / entry["test"]
        assert test.is_file(), f"{entry['name']}: {entry['test']} does not exist"
        assert f'"{entry["name"]}"' in test.read_text(), (
            f"{entry['name']}: {entry['test']} never names it"
        )


def test_the_selectable_fields_of_each_listed_operation_match_the_code() -> None:
    listed = {
        o["name"]: frozenset(o["fields"])
        for o in tomllib.loads((REPO_ROOT / LISTED).read_text())["operation"]
    }
    assert listed == RELEASE_FIELDS


def test_the_allowed_field_tree_of_each_operation_is_the_web_documents() -> None:
    """Deny by default: a field the web does not select is not in the tree. The tree is derived
    from the web's own documents, so a web change that selects more fails here until the tree (and
    the review of what it adds: nothing caller-dependent) is updated."""
    documents = web_documents()
    for name in RELEASE_SHARED_OPERATIONS:
        assert RELEASE_FIELDS[name] == field_paths(documents[name]), (
            f"{name}: the web's document selects other fields than RELEASE_FIELDS allows"
        )
