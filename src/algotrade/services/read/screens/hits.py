"""Which of the user's screeners picked an instrument in the session (``ScreenerHit``, the
Explore detail pane's "Screener hits"): every screener the user sees (``screeners``), its run
for exactly the session by THE latest-run rule (``runs``; a screener not run for it has no
hit, never an older run's), and the instrument's result in that run when it is a pick
(``runs.is_picked``). A small index says which runs picked each instrument (``PickIndex``, from
the runs' cached light rows); the result itself (its criteria, values and reasons, read from the
run's own files for that instrument only) is built when the instrument is asked for and kept in
a bounded ``HitsHeld``."""

from collections import OrderedDict
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from threading import Lock

from algotrade.services.read.context import (
    DICT_ENTRY_BYTES,
    SLOT_BYTES,
    ReadContext,
    weigh,
)
from algotrade.services.read.screens.results import (
    ScreenResult,
    load_instrument_changes,
    load_results,
)
from algotrade.services.read.screens.runs import (
    ScreenerRun,
    is_picked,
    load_latest_runs,
    run_rows,
)
from algotrade.services.read.screens.screeners import Screener, load_screeners

MAX_HELD_INSTRUMENTS = 512  # the instruments whose hits one publish keeps (oldest asked go first)


@dataclass(frozen=True)
class ScreenerHit:
    """A screener that picked the instrument in the session, and what its run stored for it."""

    screener: Screener
    result: ScreenResult


class PickIndex:
    """The user's screeners with a run for the session, and per instrument the positions (in
    ``runs``) of the runs that picked it: a tuple of small integers per pick, no result."""

    def __init__(
        self,
        runs: list[tuple[Screener, ScreenerRun]],
        picked_by: dict[str, tuple[int, ...]],
    ) -> None:
        self.runs = runs
        self.picked_by = picked_by

    def weight_bytes(self) -> int:
        """What the picks take: an id, a slot and an integer per pick (the runs are shared)."""
        return sum(
            weigh(iid) + DICT_ENTRY_BYTES + (SLOT_BYTES + 28) * len(at)
            for iid, at in self.picked_by.items()
        )


class HitsHeld:
    """The hits built so far for the instruments asked, one container per publish in
    ``ctx.cache`` (a cache entry per instrument would push every other entry out of its 32):
    bounded to ``MAX_HELD_INSTRUMENTS``, weighing what the results really take, put again when
    it grows."""

    def __init__(self) -> None:
        self._hits: OrderedDict[str, tuple[ScreenerHit, ...]] = OrderedDict()
        self._lock = Lock()

    def get(self, iid: str) -> tuple[ScreenerHit, ...] | None:
        with self._lock:
            found = self._hits.get(iid)
            if found is not None:
                self._hits.move_to_end(iid)
            return found

    def add(self, found: dict[str, tuple[ScreenerHit, ...]]) -> None:
        with self._lock:
            self._hits.update(found)
            while len(self._hits) > MAX_HELD_INSTRUMENTS:
                self._hits.popitem(last=False)

    def weight_bytes(self) -> int:
        with self._lock:
            held = list(self._hits.values())
        return sum(weigh(hit.result) + SLOT_BYTES for hits in held for hit in hits)


def load_screener_hits(
    ctx: ReadContext, instrument_ids: Sequence[str]
) -> dict[str, tuple[ScreenerHit, ...]]:
    """The hits of each of ``instrument_ids`` (by screener id; none: an empty tuple). The index of
    who picked what is built once per published state and caller; an instrument's results are read
    for it alone (from each picking run's own files), once, and kept."""
    index, key = _pick_index(ctx)
    held: HitsHeld = ctx.cache.get_or_compute((*key, "held"), HitsHeld)
    asked = list(dict.fromkeys(instrument_ids))
    out = {i: held.get(i) for i in asked}
    missing = [i for i in asked if out[i] is None]
    if missing:
        built = _build(ctx, index, missing)
        held.add(built)
        ctx.cache.put((*key, "held"), held)  # its weight changed
        out.update(built)
    return {i: hits if hits is not None else () for i, hits in out.items()}


def _pick_index(ctx: ReadContext) -> tuple[PickIndex, tuple[object, ...]]:
    """The session's pick index for the user, and its cache key (the user, the screeners' runs
    and the published state read first, ADR 0022: a saved screen or a new run is a new key)."""
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
    build: Callable[[], PickIndex] = lambda: _index(ctx, runs)  # noqa: E731
    found: PickIndex = ctx.cache.get_or_compute((*key, "index"), build)
    return found, key


def _index(ctx: ReadContext, runs: list[tuple[Screener, ScreenerRun]]) -> PickIndex:
    picked_by: dict[str, list[int]] = {}
    for n, (_, run) in enumerate(runs):
        rows = run_rows(ctx, run)
        for iid, decision in zip(rows["instrument_id"], rows["decision"], strict=True):
            if is_picked(str(decision)):
                picked_by.setdefault(str(iid), []).append(n)
    return PickIndex(runs, {i: tuple(at) for i, at in picked_by.items()})


def _build(
    ctx: ReadContext, index: PickIndex, instruments: Sequence[str]
) -> dict[str, tuple[ScreenerHit, ...]]:
    """The hits of ``instruments``, their results read in one pass over the runs that picked
    them (each run's own file, for those instruments only)."""
    wanted: dict[str, list[str]] = {}
    for iid in instruments:
        for n in index.picked_by.get(iid, ()):
            wanted.setdefault(index.runs[n][1].run_id, []).append(iid)
    runs = [run for _, run in index.runs if run.run_id in wanted]
    changes = {run.run_id: load_instrument_changes(ctx, run, wanted[run.run_id]) for run in runs}
    found = load_results(ctx, wanted, runs, changes)
    out: dict[str, list[ScreenerHit]] = {i: [] for i in instruments}
    for iid in instruments:
        for n in index.picked_by.get(iid, ()):
            screener, run = index.runs[n]
            result = found.get((run.run_id, iid))
            if result is not None and is_picked(result.decision):
                out[iid].append(ScreenerHit(screener, result))
    return {i: tuple(hits) for i, hits in out.items()}
