"""The run records behind an edge page are decoded once per run-record generation, not once per
edge per field: the answers equal the uncached ones, a saved run is seen at once, a snapshot
reader is never cached, and the site's trial count is taken once per request."""

from datetime import date
from typing import Any

import pytest

from algotrade.services.read.context import ResultCache
from algotrade.services.read.evaluation import runs as runs_module
from algotrade.services.read.evaluation.edges import load_edges
from algotrade.services.read.evaluation.runs import (
    _committed,
    load_canonical_run,
    load_edge_runs,
    load_site_trials,
)
from algotrade.services.read.evaluation.verdict import load_edge_verdict
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.tables.readers import StoreReader
from tests.unit.services.read.evaluation.conftest import (
    DOCS,
    EDGE,
    FROZEN,
    session_ctx,
    stores,
    write_run,
)

N = 6
IDS = [f"e{i}" for i in range(N)]


def _docs() -> dict[tuple[str, str, str], dict]:
    return {
        **DOCS,
        **{("site", "edges", i): {**EDGE, "id": i, "name": i.upper()} for i in IDS},
    }


def _filled(backend: MemoryBackend) -> None:
    for k, edge in enumerate(["drift", *IDS]):
        write_run(backend, f"a{k}", FROZEN, 0.6, minutes=k, edge=edge, trials_counted=3 + k)
        write_run(backend, f"b{k}", FROZEN, 0.5, minutes=40 + k, edge=edge, trials_counted=4 + k)


def _calls(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    seen: list[str] = []
    real = runs_module._read_committed

    def spy(ctx: Any, edge: Any, owner: str) -> Any:
        seen.append(f"{edge.id}:{owner}")
        return real(ctx, edge, owner)

    monkeypatch.setattr(runs_module, "_read_committed", spy)
    return seen


def test_a_page_of_edges_decodes_each_edges_records_once_however_many_fields_ask(
    backend: MemoryBackend, monkeypatch: pytest.MonkeyPatch
) -> None:
    _filled(backend)
    ctx = session_ctx(stores(backend, docs=_docs()), date(2026, 10, 1))
    seen = _calls(monkeypatch)
    edges = load_edges(ctx)
    assert len(edges) == N + 1
    for _ in range(5):  # five resolvers per edge, each judging and counting the site's trials
        for edge in edges:
            load_edge_verdict(ctx, edge)
            load_edge_runs(ctx, edge)
    assert len(seen) == len(set(seen)) <= 2 * len(edges)  # O(edges), not O(edges x resolvers)


def test_the_cached_runs_and_verdicts_equal_the_uncached_ones(
    backend: MemoryBackend, monkeypatch: pytest.MonkeyPatch
) -> None:
    _filled(backend)
    ctx = session_ctx(stores(backend, docs=_docs()), date(2026, 10, 1))
    edges = load_edges(ctx)

    def answers(c: Any) -> list[Any]:
        return [
            (load_edge_runs(c, e), load_canonical_run(c, e), load_edge_verdict(c, e)) for e in edges
        ] + [load_site_trials(c)]

    first, again = answers(ctx), answers(ctx)  # the second round is all hits
    monkeypatch.setattr(runs_module, "_committed", runs_module._read_committed)
    plain = answers(session_ctx(stores(backend, docs=_docs()), date(2026, 10, 1)))
    assert first == again == plain
    assert plain[-1] == sum(4 + k for k in range(N + 1))  # the newest canonical run's count


def test_a_run_saved_since_is_seen_by_the_next_read_not_an_older_entry(
    backend: MemoryBackend,
) -> None:
    write_run(backend, "r1", FROZEN, 0.6, minutes=1, trials_counted=2)
    cache = ResultCache()
    ctx = session_ctx(stores(backend, cache=cache), date(2026, 10, 1))
    (edge,) = load_edges(ctx)
    assert [r.run_id for r in _committed(ctx, edge, "site")] == ["r1"]
    write_run(backend, "r2", FROZEN, 0.6, minutes=9, trials_counted=8)
    fresh = session_ctx(stores(backend, cache=cache), date(2026, 10, 1))  # a later request
    assert [r.run_id for r in _committed(fresh, edge, "site")] == ["r2", "r1"]
    assert load_site_trials(fresh) == 8


def test_a_snapshot_reader_is_never_cached(
    backend: MemoryBackend, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_run(backend, "r1", FROZEN, 0.6, minutes=1)
    cache = ResultCache()
    base = stores(backend, cache=cache)
    frozen = StoreReader(backend).with_runs_frozen(["edge-eval:drift:site"])
    ctx = session_ctx(base, date(2026, 10, 1))
    ctx = type(ctx)(frozen, ctx.configs, ctx.user, ctx.session, ctx.features, cache)
    (edge,) = load_edges(ctx)
    seen = _calls(monkeypatch)
    _committed(ctx, edge, "site")
    _committed(ctx, edge, "site")
    assert len(seen) == 2


def test_the_site_trial_count_is_taken_once_per_request(
    backend: MemoryBackend, monkeypatch: pytest.MonkeyPatch
) -> None:
    _filled(backend)
    ctx = session_ctx(stores(backend, docs=_docs()), date(2026, 10, 1))
    taken: list[int] = []
    real = runs_module._site_trials
    monkeypatch.setattr(runs_module, "_site_trials", lambda c: taken.append(1) or real(c))
    for _ in range(50):
        load_site_trials(ctx)
    assert len(taken) == 1
