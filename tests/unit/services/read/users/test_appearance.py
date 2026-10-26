"""The stored theme: valid, missing, malformed. The loader reads only ``configs`` and ``user``."""

from typing import Any, cast

import pytest

from algotrade.config.user import UserContext
from algotrade.services.read.context import Stores
from algotrade.services.read.users.appearance import Appearance, load_appearance
from algotrade.storage.configs.files import MemoryConfigStore


def ctx_of(document: Any) -> Stores:
    docs = {} if document is None else {("me", "preferences", "preferences"): document}
    fields = {"configs": MemoryConfigStore(docs), "user": UserContext("me")}
    return cast(Stores, type("Ctx", (), fields))


@pytest.mark.parametrize("theme", ["light", "dark", "system"])
def test_a_stored_theme_is_read(theme: str) -> None:
    assert load_appearance(ctx_of({"appearance": {"theme": theme}})) == Appearance(theme)


@pytest.mark.parametrize(
    "document",
    [
        None,
        {},
        {"views": {}},
        {"appearance": {}},
        {"appearance": {"theme": "Dark"}},
        {"appearance": {"theme": "sepia"}},
        {"appearance": {"theme": 3}},
        {"appearance": "dark"},
    ],
)
def test_a_missing_or_malformed_choice_reads_as_system(document: Any) -> None:
    assert load_appearance(ctx_of(document)) == Appearance("system")
