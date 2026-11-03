"""Whether the viewer may be served a setup at all (ADR 0084 decision 1, ADR 0088 decision
20): a setup with a committed run (the site's, or the viewer's own for their own edge) that
joined outcome rows, or read a rule field (gate, entry, case, schedule; ADR 0088 decision 20),
under a licence the viewer does not hold (``EdgeRun.evidence_licence``, the strictest of the
outcome rows' ``licence`` and the rules' fields, of every trial kind) is not listed for them,
has no verdict and adds no pick to their Ideas, never an UNKNOWN or a blank. The strictest of
every open run decides, not the canonical one: ``edge_runs`` serves them all, and the history
slice is a separate run job only the owner is served (``load_history_runs`` below, ADR 0088 d11).
Only the outcome and the rules gate it: the screen's and universe's fields keep their per-column
redaction (ADR 0064 decision 10; ADR 0088 decision B), so a setup over a personal
screener field stays listed. A setup with no run has no evidence to protect."""

from algotrade.config.edges.document import job_name
from algotrade.config.edges.positions.chain import OPTION_HISTORY
from algotrade.config.user import SITE_USER
from algotrade.services.read.context import Stores
from algotrade.services.read.evaluation import runs
from algotrade.services.read.evaluation.edges import Edge, held_licences
from algotrade.storage.runs import RunStatus


def evidence_visible(ctx: Stores, edge: Edge) -> bool:
    """Whether the viewer holds the licence of every committed open run's outcome rows of ``edge``.
    A run from before the price-source split (``EdgeRun.pre_split``: it may have joined history
    rows beside Cboe's) is ignored: the open verdict is the Cboe-only run's (ADR 0088 d11); the
    history slice is a separate run job ``edge_runs`` never lists."""
    held = held_licences(ctx)
    return all(
        r.evidence_licence in held for r in runs.load_edge_runs(ctx, edge) if not r.pre_split
    )


def load_history_runs(ctx: Stores, edge: Edge) -> tuple[runs.EdgeRun, ...]:
    """Every committed history-slice run of ``edge`` (bought ``option_history`` rows, ADR 0088
    d11), newest first, served only when the viewer holds the run's evidence licence (the owner,
    decision 12): to anyone else it is simply not listed, never an UNKNOWN or a blank."""
    held = held_licences(ctx)
    found = [
        runs.run_of_record(r, edge, owner)
        for owner in dict.fromkeys([ctx.user.user_id, SITE_USER])
        for r in ctx.reader.runs(job_name(edge.id, owner, OPTION_HISTORY))
        if r.status is RunStatus.COMPLETE
    ]
    shown = [r for r in found if r.evidence_licence in held]
    return tuple(sorted(shown, key=lambda r: r.knowledge_ts, reverse=True))
