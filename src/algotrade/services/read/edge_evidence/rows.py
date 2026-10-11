"""The rows an evidence section reads (ADR 0064): the stored rows of an edge's official run for
one screen at one holding period, at the verdict's basis (``basis.official_basis``: the
official run, a site edge's canonical run or the user's own latest, and the screen and holding
period ADR 0065 fixed before the out-of-sample figures are read; a section never re-chooses).
A hidden copy's rows are already cut to the in-sample side by ``runs.load_run_rows``."""

from dataclasses import dataclass

from algotrade.services.read.context import Stores
from algotrade.services.read.edge_evidence.basis import OfficialBasis
from algotrade.services.read.evaluation import runs
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


def load_basis_rows(ctx: Stores, basis: OfficialBasis) -> BasisRows:
    """The rows of ``basis``'s run for its screen and holding period."""
    run, key = basis.run, basis.key
    if run is None or key is None:
        why = "no official result yet" if run is None else "the verdict fixes no basis"
        return BasisRows(run, None, None, basis.hidden, (), f"{basis.edge.id}: {why}")
    variant, horizon = key
    rows = tuple(
        r
        for r in runs.load_run_rows(ctx, run)
        if r.edge_variant == runs.MAIN
        and r.role != runs.BASELINE
        and (r.variant, r.horizon_sessions) == key
    )
    return BasisRows(run, variant, horizon, run.oos_hidden, rows)
