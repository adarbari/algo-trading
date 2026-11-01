"""Whether the viewer may be served a site setup at all (ADR 0084 decision 1, ADR 0088 decision
20): a setup whose canonical run joined outcome rows under a licence the viewer does not hold
(``EdgeRun.evidence_licence``, the strictest ``licence`` of the outcome rows the run read) is not
listed for them, has no verdict and adds no pick to their Ideas, never an UNKNOWN or a blank. Only
the outcome gates it: the screen's and universe's fields keep their per-column redaction (ADR
0064 decision 10; ADR 0088 decision B), so a setup over a personal screener field stays listed.
A setup with no canonical run has no evidence to protect; a user's own edge is theirs."""

from algotrade.config.site.settings import load_users
from algotrade.services.licences import held_by
from algotrade.services.read.context import Stores
from algotrade.services.read.evaluation import runs
from algotrade.services.read.evaluation.edges import Edge


def evidence_visible(ctx: Stores, edge: Edge) -> bool:
    """Whether the viewer holds the licence of ``edge``'s canonical run's outcome rows."""
    if edge.mine:
        return True
    run = runs.load_canonical_run(ctx, edge).run
    if run is None:
        return True
    return run.evidence_licence in held_by(load_users(ctx.configs), ctx.user.user_id)
