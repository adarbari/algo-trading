"""The serving release's read path (ADR 0077 decision 23): no loader keys on the live commit
sequence, and the operations answered from the release are exactly the ones
``architecture/release_shared_ops.toml`` lists, each a SHARED operation with a reason and a test."""

import re
import tomllib

from algotrade_api.graphql.response_cache import RELEASE_SHARED_OPERATIONS, SHARED_OPERATIONS
from tests.conftest import REPO_ROOT

LISTED = "architecture/release_shared_ops.toml"


def test_no_read_model_loader_keys_on_the_live_sequence() -> None:
    """A loader's cache key holds ``reader.version()``: ``("pin", X)`` for a release read,
    ``("live", seq)`` otherwise. ``visible_seq()`` would stay live under a pin and recompute on
    every commit (ADR 0077 decision 23)."""
    found = [
        f"{path.relative_to(REPO_ROOT)}:{n}"
        for path in sorted((REPO_ROOT / "src/algotrade/services/read").rglob("*.py"))
        for n, line in enumerate(path.read_text().splitlines(), start=1)
        if re.search(r"\bvisible_seq\(\)", line) and not line.lstrip().startswith("#")
    ]
    assert not found, (
        f"visible_seq() under services/read: {found}. Key on reader.version() instead "
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
