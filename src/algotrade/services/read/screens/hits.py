"""Which of the user's screeners picked an instrument in the session (``ScreenerHit``, the
Explore detail pane's "Screener hits"): every screener the user sees (``screeners``), its run
for exactly the session by THE latest-run rule (``runs``; a screener not run for it has no
hit, never an older run's), and the instrument's result in that run when it is a pick
(``runs.is_picked``). One read of the session's results for every instrument asked."""

from collections.abc import Sequence
from dataclasses import dataclass

from algotrade.services.read.context import ReadContext
from algotrade.services.read.screens.results import ScreenResult, load_results, load_run_changes
from algotrade.services.read.screens.runs import is_picked, load_latest_runs
from algotrade.services.read.screens.screeners import Screener, load_screeners


@dataclass(frozen=True)
class ScreenerHit:
    """A screener that picked the instrument in the session, and what its run stored for it."""

    screener: Screener
    result: ScreenResult


def load_screener_hits(
    ctx: ReadContext, instrument_ids: Sequence[str]
) -> dict[str, tuple[ScreenerHit, ...]]:
    """The hits of each of ``instrument_ids`` (by screener id; none: an empty tuple)."""
    ids = list(dict.fromkeys(instrument_ids))
    screeners = load_screeners(ctx)
    latest = load_latest_runs(ctx, [(s.owner, s.id) for s in screeners])
    ran = [(s, latest[(s.owner, s.id)].run) for s in screeners]
    runs = [(s, run) for s, run in ran if run is not None]
    changes = {run.run_id: load_run_changes(ctx, run) for _, run in runs}
    found = load_results(
        ctx, {run.run_id: ids for _, run in runs}, [run for _, run in runs], changes
    )
    out: dict[str, list[ScreenerHit]] = {i: [] for i in ids}
    for screener, run in runs:
        for iid in ids:
            result = found.get((run.run_id, iid))
            if result is not None and is_picked(result.decision):
                out[iid].append(ScreenerHit(screener, result))
    return {i: tuple(hits) for i, hits in out.items()}
