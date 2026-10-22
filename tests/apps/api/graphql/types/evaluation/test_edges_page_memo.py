"""The EdgesPage query through the real seam (a ``RequestContext``, whose ``stores()`` is the
``StoreContext`` every edge resolver shares, pinned and unpinned): the edge documents are parsed
once per user, the site trials counted at most once, each edge's run records decoded once per
owner per request, and a second request has its own memo (#829 memoised only a ``ReadContext``,
which these resolvers never get)."""

import asyncio
from collections import Counter
from datetime import date
from typing import Any

import pytest

from algotrade.config.site.users import Role, UserRecord
from algotrade.config.user import UserContext
from algotrade.services.read.context import StoreContext, open_stores
from algotrade.services.read.evaluation import edges as edges_module
from algotrade.services.read.evaluation import runs as runs_module
from algotrade.services.read.evaluation import verdict as verdict_module
from algotrade.services.read.serving.current import CurrentRelease
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.tables.readers import StoreReader
from algotrade_api.graphql.context import RequestContext
from algotrade_api.graphql.schema import schema
from tests.unit.services.read.evaluation.conftest import DOCS, EDGE, FROZEN, write_run
from tests.unit.services.read.evaluation.conftest import stores as stores_of

ANA = UserRecord("me", Role.TRADER)
IDS = [f"e{i}" for i in range(6)]
PAGE = "query EdgesPage { edges { id verdict { verdict } runs { runId } } }"
RELEASE = CurrentRelease("r1", date(2026, 10, 1), 1, "hash")


def _docs() -> dict[tuple[str, str, str], dict[str, Any]]:
    return {**DOCS, **{("site", "edges", i): {**EDGE, "id": i, "name": i.upper()} for i in IDS}}


def _opener(backend: MemoryBackend) -> Any:
    def open_(user: UserContext) -> StoreContext:
        return open_stores(StoreReader(backend), stores_of(backend, docs=_docs()).configs, user)

    return open_


def _request(backend: MemoryBackend, pinned: bool) -> RequestContext:
    def read(user: UserContext, requested: date | None, **_: Any) -> Any:
        raise AssertionError("an edge resolver needs no session")

    return RequestContext(
        read, ANA, _opener(backend), RELEASE if pinned else None, None, None, pinned
    )


@pytest.mark.parametrize("pinned", [False, True])
def test_the_page_reads_each_thing_once_per_request(
    pinned: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    backend = MemoryBackend()
    for k, edge in enumerate(["drift", *IDS]):
        write_run(backend, f"a{k}", FROZEN, 0.6, minutes=k, edge=edge, trials_counted=3 + k)
        write_run(backend, f"b{k}", FROZEN, 0.5, minutes=40 + k, edge=edge, trials_counted=4 + k)
    parses: Counter[str] = Counter()
    decoded: Counter[tuple[str, str]] = Counter()
    trials: list[int] = []
    real_load, real_read, real_trials = (
        edges_module.loading.load_edges,
        runs_module._read_committed,
        runs_module._site_trials,
    )

    def load(configs: Any, user: str = "site", catalog: Any = None) -> Any:
        parses[user] += 1
        return real_load(configs, user, catalog)

    def read(ctx: Any, edge: Any, owner: str) -> Any:
        decoded[(edge.id, owner)] += 1
        return real_read(ctx, edge, owner)

    monkeypatch.setattr(edges_module.loading, "load_edges", load)
    monkeypatch.setattr(runs_module, "_read_committed", read)
    monkeypatch.setattr(runs_module, "_site_trials", lambda c: trials.append(1) or real_trials(c))

    first = _request(backend, pinned)
    result = asyncio.run(schema.execute(PAGE, context_value=first))
    assert result.errors is None and len(result.data["edges"]) == len(IDS) + 1  # type: ignore[index]
    assert parses["me"] == 1 and parses["site"] <= 1
    assert len(trials) <= 1
    assert decoded and max(decoded.values()) == 1  # per edge per owner, once per request
    again = _request(backend, pinned)
    asyncio.run(schema.execute(PAGE, context_value=again))
    assert parses["me"] == 2  # a second request: its own memo, nothing carried over
    assert first.stores().memo is not again.stores().memo  # type: ignore[union-attr]


def test_the_document_query_returns_the_ids_asked_and_never_judges(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``EdgeDocument`` (the builder's read): ``edges(ids:)`` serves only those documents, and
    with no ``verdict`` or ``runs`` selected no verdict is judged and no run record is read."""
    backend = MemoryBackend()
    judged: list[str] = []
    read_runs: list[str] = []
    real_verdict, real_read = verdict_module.load_edge_verdict, runs_module._read_committed
    monkeypatch.setattr(
        verdict_module, "load_edge_verdict", lambda c, e: judged.append(e.id) or real_verdict(c, e)
    )
    monkeypatch.setattr(
        runs_module, "_read_committed", lambda c, e, o: read_runs.append(e.id) or real_read(c, e, o)
    )
    query = (
        "query EdgeDocument($ids: [String!]!) { edges(ids: $ids) "
        "{ id name state mine extends definition { picks } } }"
    )
    result = asyncio.run(
        schema.execute(
            query, variable_values={"ids": ["e2"]}, context_value=_request(backend, False)
        )
    )
    assert result.errors is None
    assert [e["id"] for e in result.data["edges"]] == ["e2"]  # type: ignore[index]
    assert judged == [] and read_runs == []
    everything = asyncio.run(
        schema.execute("{ edges { id } }", context_value=_request(backend, False))
    )
    assert len(everything.data["edges"]) == len(IDS) + 1  # type: ignore[index]
