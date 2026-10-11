"""The rows an evidence section reads (ADR 0064): the stored rows of an edge's official run for
one screen at one holding period, resolved the way the verdict resolves them (a site edge: the
canonical run; the user's own edge: their latest run; a hidden copy's rows already cut to the
in-sample side by ``runs.load_run_rows``) and at the verdict's basis unless the caller names
one (ADR 0065: ``verdict.choose_basis``, fixed before the out-of-sample figures are read)."""

from dataclasses import dataclass, replace

from algotrade.config.site.settings import load_verdict
from algotrade.services.read.context import Stores
from algotrade.services.read.evaluation import runs, verdict, versions
from algotrade.services.read.evaluation.edges import Edge
from algotrade.services.read.evaluation.runs import EdgeRow, EdgeRun


@dataclass(frozen=True)
class BasisRows:
    """The ``rows`` of the main edge variant's screen ``variant`` at ``horizon`` sessions (every
    slice, cost rows included) from ``run``; ``hidden``: the run's out-of-sample result is
    withheld, so the rows are the in-sample side's only. No run, or no basis to read at: no rows
    and the ``reason``."""

    run: EdgeRun | None
    variant: str | None
    horizon: int | None
    hidden: bool
    rows: tuple[EdgeRow, ...]
    reason: str = ""


def load_basis_rows(
    ctx: Stores, edge: Edge, variant: str | None = None, horizon: int | None = None
) -> BasisRows:
    """The official run of ``edge`` and its rows for the screen and holding period asked for
    (both or neither: the verdict's basis)."""
    if edge.mine:
        run, why = versions.own_run(ctx, edge), f"{edge.id} has no run of yours yet"
    else:
        found = runs.load_canonical_run(ctx, edge)
        run, why = found.run, f"{edge.id} has no official result yet"
    if run is None:
        return BasisRows(None, None, None, False, (), why)
    served = runs.load_run_rows(ctx, run)
    main = [r for r in served if r.edge_variant == runs.MAIN and r.role != "baseline"]
    if variant is None or horizon is None:
        own = [replace(r, exploratory=False) for r in main] if edge.mine else main
        choice = verdict.choose_basis(
            own,
            load_verdict(ctx.configs),
            verdict.Declared(edge.promoted, edge.basis_horizon),
            bool(edge.baselines),
        )
        if choice.key is None:
            return BasisRows(run, None, None, run.oos_hidden, (), choice.reason)
        variant, horizon = choice.key
    rows = tuple(r for r in main if r.variant == variant and r.horizon_sessions == horizon)
    return BasisRows(run, variant, horizon, run.oos_hidden, rows)
