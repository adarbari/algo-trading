"""The official run and basis every section of an edge's result reads (ADR 0064, 0065): the same
run and basis the verdict judges, and NOT_RUN with the reason when there is none."""

from algotrade.services.read.edge_evidence.basis import official_basis
from algotrade.services.read.evaluation import versions
from algotrade.services.read.evaluation.edges import load_edge
from algotrade.services.read.values import UnknownCode
from algotrade.storage.backends.memory import MemoryBackend
from tests.unit.services.read.evaluation.conftest import FROZEN, row, stores, write_run
from tests.unit.services.read.evaluation.test_versions import (
    ctx_for,
    mine,
    with_copy,
    write_own_run,
)


def test_a_site_edge_is_read_at_the_basis_its_verdict_rests_on(backend: MemoryBackend) -> None:
    write_run(backend, "r1", FROZEN, 0.6)
    ctx = stores(backend)
    edge = load_edge(ctx, "drift")
    assert edge is not None
    found = official_basis(ctx, edge)
    assert found.run is not None and found.run.run_id == "r1"
    assert (found.key, found.split_from, found.hidden, found.unknown) == (
        ("momo", 20), FROZEN, False, None,
    )  # fmt: skip
    assert versions.load_verdict(ctx, edge).basis == "momo, 20 trading days"


def test_no_official_run_is_not_run_never_an_older_or_exploratory_one(
    backend: MemoryBackend,
) -> None:
    write_run(backend, "other", None, 0.6)  # a run at no frozen split is not canonical
    ctx = stores(backend)
    edge = load_edge(ctx, "drift")
    assert edge is not None
    found = official_basis(ctx, edge)
    assert (found.run, found.key) == (None, None)
    assert found.unknown is not None and found.unknown.code is UnknownCode.NOT_RUN


def test_candidates_a_run_cannot_rank_have_no_basis_and_the_reason_is_the_admins(
    backend: MemoryBackend,
) -> None:
    several = [row("momo", k, 0.5, FROZEN, horizon_sessions=15) for k in ("all", "frozen")]
    write_run(backend, "r1", FROZEN, 0.6, extra=several)  # two horizons, no in-sample rows
    ctx = stores(backend)
    edge = load_edge(ctx, "drift")
    assert edge is not None
    found = official_basis(ctx, edge)
    assert found.run is not None and found.key is None
    assert found.unknown is not None and found.unknown.code is UnknownCode.NOT_RUN
    assert "predates the in-sample figures" in found.unknown.cause.text
    assert "predates" not in found.unknown.public_reason  # a trader reads the generic words


def test_a_hidden_copy_has_a_basis_from_the_in_sample_rows_it_is_served(
    backend: MemoryBackend,
) -> None:
    write_own_run(backend)
    ctx = ctx_for(backend, with_copy())
    found = official_basis(ctx, mine(ctx))
    assert found.run is not None and found.run.oos_hidden and found.hidden
    assert found.key == ("momo", 20)


def test_a_copy_that_was_never_run_is_not_run() -> None:
    ctx = ctx_for(MemoryBackend(), with_copy())
    found = official_basis(ctx, mine(ctx))
    assert found.run is None and found.unknown is not None
    assert found.unknown.code is UnknownCode.NOT_RUN and found.hidden
