"""The variant grid (ADR 0065): every screen the run tried at every holding period, the
verdict's basis marked official, every other out-of-sample figure flagged as not the pre-chosen
test, and no out-of-sample figure at all for a hidden copy."""

from algotrade.services.read.edge_ledger.variants import load_edge_trials
from algotrade.services.read.evaluation.edges import load_edge
from algotrade.services.read.values import UnknownCode
from algotrade.storage.backends.memory import MemoryBackend
from tests.unit.services.read.edge_ledger.conftest import context
from tests.unit.services.read.evaluation.conftest import FROZEN, row, write_run
from tests.unit.services.read.evaluation.test_versions import write_own_run


def test_the_grid_marks_the_basis_and_flags_the_other_out_of_sample_figures() -> None:
    backend = MemoryBackend()
    extra = [
        row("momo", "in_sample", 0.5, FROZEN),
        row("alt", "in_sample", 0.45, FROZEN),
        row("alt", "all", 0.4, FROZEN),
        row("alt", "frozen", 0.9, FROZEN),  # the better out-of-sample figure is not the test
    ]
    write_run(backend, "site1", FROZEN, 0.6, extra=extra)
    ctx = context(backend)
    edge = load_edge(ctx, "drift")
    assert edge is not None
    grid = load_edge_trials(ctx, edge)
    assert grid.unknown is None and grid.basis == "momo, 20 trading days" and grid.trials == 1
    alt, momo = grid.rows
    assert (alt.variant, alt.official, alt.not_pre_chosen) == ("alt", False, True)
    assert (momo.variant, momo.official, momo.not_pre_chosen) == ("momo", True, False)
    assert alt.out_of_sample is not None and alt.out_of_sample.win_rate == 0.9
    assert momo.in_sample is not None and momo.in_sample.lift_pts is not None
    assert momo.all is not None and momo.out_of_sample is not None


def test_an_edge_with_no_official_run_has_no_grid() -> None:
    ctx = context(MemoryBackend())
    edge = load_edge(ctx, "drift")
    assert edge is not None
    grid = load_edge_trials(ctx, edge)
    assert grid.rows == () and grid.unknown is not None
    assert grid.unknown.code is UnknownCode.NOT_RUN


def test_a_hidden_copys_grid_has_no_out_of_sample_figure() -> None:
    backend = MemoryBackend()
    write_own_run(backend)
    docs = {("me", "edges", "mine"): {"extends": "drift", "screeners": ["momo"]}}
    ctx = context(backend, "me", docs)
    edge = load_edge(ctx, "mine")
    assert edge is not None and edge.oos_hidden
    grid = load_edge_trials(ctx, edge)
    assert grid.oos_hidden and grid.rows
    assert all(r.out_of_sample is None and not r.not_pre_chosen for r in grid.rows)
