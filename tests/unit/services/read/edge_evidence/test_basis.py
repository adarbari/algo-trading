"""The official basis (ADR 0065) is the verdict's own run and screen, read for every evidence
section, never chosen again."""

from algotrade.services.read.edge_evidence.basis import official_basis
from algotrade.services.read.evaluation.edges import load_edge
from algotrade.services.read.values import UnknownCode
from algotrade.storage.backends.memory import MemoryBackend
from tests.unit.services.read.edge_evidence.conftest import context


def test_the_basis_is_the_canonical_runs_screen_and_period(backend: MemoryBackend) -> None:
    ctx = context(backend)
    edge = load_edge(ctx, "drift")
    assert edge is not None
    found = official_basis(ctx, edge)
    assert found.run is not None and found.run.run_id == "site1"
    assert found.key == ("momo", 20) and found.not_run is None
    assert official_basis(ctx, edge) is found  # read once per request


def test_an_edge_with_no_official_run_says_not_run() -> None:
    ctx = context(MemoryBackend())
    edge = load_edge(ctx, "drift")
    assert edge is not None
    found = official_basis(ctx, edge)
    assert found.run is None and found.key is None
    assert found.not_run is not None and found.not_run.code is UnknownCode.NOT_RUN
