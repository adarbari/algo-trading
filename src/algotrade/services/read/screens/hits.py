"""Which of the user's screeners picked an instrument in the session (``ScreenerHit``, the
Explore detail pane's "Screener hits"): every screener the user sees (``screeners``), its run
for exactly the session by THE latest-run rule (``runs``; a screener not run for it has no
hit, never an older run's), and the instrument's result in that run when it is a pick
(``runs.is_picked``). One read of the session's picks, indexed by instrument."""

from collections.abc import Sequence
from dataclasses import dataclass

from algotrade.services.read.context import ReadContext
from algotrade.services.read.screens.results import ScreenResult, load_results, load_run_changes
from algotrade.services.read.screens.runs import (
    ScreenerRun,
    is_picked,
    load_latest_runs,
    run_rows,
)
from algotrade.services.read.screens.screeners import Screener, load_screeners


@dataclass(frozen=True)
class ScreenerHit:
    """A screener that picked the instrument in the session, and what its run stored for it."""

    screener: Screener
    result: ScreenResult


def load_screener_hits(
    ctx: ReadContext, instrument_ids: Sequence[str]
) -> dict[str, tuple[ScreenerHit, ...]]:
    """The hits of each of ``instrument_ids`` (by screener id; none: an empty tuple): a lookup in
    the session's index of every pick (``_session_hits``), built once per published state and
    caller, not once per instrument."""
    index = _session_hits(ctx)
    return {i: index.get(i, ()) for i in dict.fromkeys(instrument_ids)}


def _session_hits(ctx: ReadContext) -> dict[str, tuple[ScreenerHit, ...]]:
    """Every pick of the user's screeners in the session, by instrument id. The stored value rows
    of a run are read for the instruments it picked (a few hundred), once for all of them:
    reading them per asked instrument cost 0.6 s each (every row group of 4.9 million value
    rows), and the hits of one session are the same for every ticker opened. Kept in
    ``ctx.cache`` under the user (the licence gate is applied per viewer), the runs of the
    screeners they see and the published state (read first, ADR 0022), so a saved screen or a
    new run is a new key."""
    screeners = load_screeners(ctx)
    latest = load_latest_runs(ctx, [(s.owner, s.id) for s in screeners])
    runs = [(s, r) for s in screeners if (r := latest[(s.owner, s.id)].run) is not None]
    key = (
        "screener-hits",
        ctx.user.user_id,
        ctx.session.date,
        ctx.reader.own_run,
        ctx.reader.visible_seq(),
        tuple(run.run_id for _, run in runs),
    )
    found: dict[str, tuple[ScreenerHit, ...]] = ctx.cache.get_or_compute(
        key, lambda: _build(ctx, runs)
    )
    return found


def _build(
    ctx: ReadContext, runs: list[tuple[Screener, ScreenerRun]]
) -> dict[str, tuple[ScreenerHit, ...]]:
    changes = {run.run_id: load_run_changes(ctx, run) for _, run in runs}
    picked: dict[str, list[str]] = {}
    for _, run in runs:
        rows = run_rows(ctx, run)
        picked[run.run_id] = [
            str(i)
            for i, d in zip(rows["instrument_id"], rows["decision"], strict=True)
            if is_picked(str(d))
        ]
    found = load_results(ctx, picked, [run for _, run in runs], changes)
    out: dict[str, list[ScreenerHit]] = {}
    for screener, run in runs:
        for iid in picked[run.run_id]:
            result = found.get((run.run_id, iid))
            if result is not None and is_picked(result.decision):
                out.setdefault(iid, []).append(ScreenerHit(screener, result))
    return {i: tuple(hits) for i, hits in out.items()}
