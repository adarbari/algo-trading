"""A release answer equals the live answer pinned at the release's sequence (ADR 0077 decision
2): after commits that change what a live read shows, the listed operations still answer what the
store showed at X, and a plain app whose every read is pinned at X (no release involved) agrees."""

from datetime import date
from functools import partial
from typing import Any

import pytest
from fastapi.testclient import TestClient

from algotrade.config.user import UserContext
from algotrade.services.read.context import ReadContext, ResultCache, open_context
from algotrade_api import main
from algotrade_api.deps import ApiSettings, ReadStore
from algotrade_api.main import create_app
from tests.contract.api.release_reads.test_cache_survives_commits import (
    OPERATIONS,
    World,
    five_commits,
    world,  # noqa: F401 (the fixture)
)
from tests.helpers.api_store import as_user


def pinned_app(w: World, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """An app with no release whose every read context is pinned at the release's sequence and
    resolves the release's session by default: the "live answer pinned at X"."""
    manifest = w.releases.open(w.release_id).manifest  # type: ignore[union-attr]
    session = date.fromisoformat(manifest.session)

    def reads(store: ReadStore, cache: ResultCache) -> Any:
        pinned = store.reader.pinned(manifest.seq)

        def opener(user: UserContext, requested: Any = None) -> ReadContext:
            return partial(open_context, pinned, store.configs, cache=cache)(
                user, requested or session
            )

        return opener

    monkeypatch.setattr(main, "_reads", reads)
    return TestClient(
        create_app(ApiSettings("memory://", "config"), w.store, authenticator=as_user())
    )


def test_the_release_answer_equals_the_live_answer_pinned_at_x_after_commits(
    world: World,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    five_commits(world)  # live now shows S+1 and a restated S: the release must not
    reference = pinned_app(world, monkeypatch)
    for name, (document, variables) in OPERATIONS.items():
        served = world.post(document, variables)
        expected = reference.post("/graphql", json={"query": document, "variables": variables})
        assert served.status_code == expected.status_code == 200, name
        assert served.json() == expected.json(), name
