"""Whether the viewer may be served a setup at all (ADR 0084 decision 1, ADR 0088 decision
20): a setup with a committed run (the site's, or the viewer's own for their own edge) that
joined outcome rows under a licence the viewer does not hold (``EdgeRun.evidence_licence``, the
strictest ``licence`` of the outcome rows the run read) is not listed for them, has no verdict
and adds no pick to their Ideas, never an UNKNOWN or a blank. The strictest of every run decides,
not the canonical one: ``edge_runs`` serves them all, and a history slice is a trial only the
owner sees (owner answer 1). Only the outcome gates it: the screen's and universe's fields keep
their per-column redaction (ADR 0064 decision 10; ADR 0088 decision B), so a setup over a
personal screener field stays listed. A setup with no run has no evidence to protect."""

from algotrade.config.site.settings import load_users
from algotrade.services.licences import held_by
from algotrade.services.read.context import Stores, once_per_request
from algotrade.services.read.evaluation import runs
from algotrade.services.read.evaluation.edges import Edge


def _held(ctx: Stores) -> frozenset[str]:
    """The viewer's held licences, once per request."""
    key = ("held-licences", ctx.user.user_id)
    return once_per_request(ctx, key, lambda: held_by(load_users(ctx.configs), ctx.user.user_id))


def evidence_visible(ctx: Stores, edge: Edge) -> bool:
    """Whether the viewer holds the licence of every committed run's outcome rows of ``edge``."""
    held = _held(ctx)
    return all(r.evidence_licence in held for r in runs.load_edge_runs(ctx, edge))
