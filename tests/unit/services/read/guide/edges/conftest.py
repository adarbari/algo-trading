"""The shipped site configs as a read context, and the same over a store that also holds a
user's draft edge (``DRAFT_USER``): the Guide must never show the draft."""

from collections.abc import Mapping
from typing import Any

import pytest

from algotrade.config.user import SITE_USER, UserContext
from algotrade.data import StoreReader
from algotrade.services.read.context import StoreContext, open_stores
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.configs.files import FileConfigStore
from tests.conftest import REPO_ROOT

DRAFT_USER = "guide_draft_user"
DRAFT_ID = "guide_draft_edge"
DRAFT = {
    "id": DRAFT_ID,
    "name": "A user's draft",
    "thesis": "A trader's own idea, never the site's.",
    "extends": "momentum_12_1",
}


class WithDraft:
    """The shipped store plus one user's draft edge file (``config/users/<id>/edges/<id>.toml``)."""

    def __init__(self, inner: FileConfigStore) -> None:
        self._inner = inner

    def load(self, scope: str, kind: str, name: str) -> Mapping[str, Any] | None:
        if (scope, kind, name) == (DRAFT_USER, "edges", DRAFT_ID):
            return DRAFT
        return self._inner.load(scope, kind, name)

    def names(self, scope: str, kind: str) -> list[str]:
        if (scope, kind) == (DRAFT_USER, "edges"):
            return [DRAFT_ID]
        return self._inner.names(scope, kind)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)


@pytest.fixture
def site() -> StoreContext:
    """The shipped site configs; a fresh context (and cache) per test."""
    store = FileConfigStore(REPO_ROOT / "config")
    return open_stores(StoreReader(MemoryBackend()), store, UserContext(SITE_USER))


@pytest.fixture
def with_draft() -> StoreContext:
    store = WithDraft(FileConfigStore(REPO_ROOT / "config"))
    return open_stores(StoreReader(MemoryBackend()), store, UserContext(DRAFT_USER))  # type: ignore[arg-type]
