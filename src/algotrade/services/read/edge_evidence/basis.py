"""The official run of an edge and the basis its verdict rests on (ADR 0065), for every evidence
section that must show the verdict's own test.

``official_basis`` reads what the verdict reads: a site edge's canonical run, the user's own edge's
latest run, and the ``(screen, holding period)`` ``verdict.choose_basis`` fixes from that run's
in-sample rows (``versions.basis_of``, the comparison's rule too). It never chooses again: a
section that needs another screen or period is a different object (the variant grid), and a run
the verdict has none of is ``NOT_RUN`` with the reason, never an older or exploratory one. Read
once per request where the context keeps a scratch (``ReadContext.memo``)."""

from dataclasses import dataclass

from algotrade.services.read.context import ReadContext, Stores
from algotrade.services.read.evaluation import runs, versions
from algotrade.services.read.evaluation.edges import Edge
from algotrade.services.read.evaluation.runs import EdgeRow, EdgeRun
from algotrade.services.read.values import Unknown


@dataclass(frozen=True)
class OfficialBasis:
    """``run``: the official run (None: ``not_run`` says why); ``key``: the basis's screen and
    holding period (None: ``reason`` says why none can be fixed); ``rows``: the run's rows as
    served to the viewer (a hidden copy's: in-sample only)."""

    run: EdgeRun | None
    key: tuple[str, int] | None
    reason: str = ""
    not_run: Unknown | None = None
    rows: tuple[EdgeRow, ...] = ()


def _read(ctx: Stores, edge: Edge) -> OfficialBasis:
    if edge.mine:
        run, not_run = versions.own_run(ctx, edge), None
        if run is None:
            return OfficialBasis(None, None, "You have not run this edge yet")
    else:
        found = runs.load_canonical_run(ctx, edge)
        run, not_run = found.run, found.not_run
        if run is None:
            return OfficialBasis(None, None, "No official result yet", not_run)
    rows = runs.load_run_rows(ctx, run)
    choice = versions.basis_of(ctx, edge, rows)
    return OfficialBasis(run, choice.key, choice.reason, None, rows)


def official_basis(ctx: Stores, edge: Edge) -> OfficialBasis:
    """The official run of ``edge`` and its verdict's basis (memoised per request)."""
    if not isinstance(ctx, ReadContext):
        return _read(ctx, edge)
    key = ("official_basis", edge.id, edge.mine, ctx.user.user_id)
    if key not in ctx.memo:
        ctx.memo[key] = _read(ctx, edge)
    found: OfficialBasis = ctx.memo[key]
    return found
