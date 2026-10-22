"""Which of the user's screeners picked an instrument in the session (``ScreenerHit``, the
Explore detail pane's "Screener hits"): every screener the user sees (``screeners``), its run
for exactly the session by THE latest-run rule (``runs``; a screener not run for it has no
hit, never an older run's), and the instrument's result in that run when it is a pick
(``runs.is_picked``). A small index says which runs picked each instrument (``PickIndex``, from
the runs' cached picks); the result itself (its criteria, values and reasons, read from the
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
    load_latest_runs,
    picked_mask,
    run_picks,
)
from algotrade.services.read.screens.screeners import Screener, load_screeners
from algotrade.services.screening.rule_results import is_picked

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
    bounded to ``MAX_HELD_INSTRUMENTS`` (the oldest asked go first), built once per instrument
    even when threads ask together (a lock per instrument), weighing what the results take as a
    running total (weighed outside the cache's lock, subtracted on eviction)."""

    def __init__(self) -> None:
        self._hits: OrderedDict[str, tuple[ScreenerHit, ...]] = OrderedDict()
        self._weights: dict[str, int] = {}
        self._bytes = 0
        self._lock = Lock()
        self._flights: dict[str, Lock] = {}

    def _get(self, iid: str) -> tuple[ScreenerHit, ...] | None:
        with self._lock:
            found = self._hits.get(iid)
            if found is not None:
                self._hits.move_to_end(iid)
            return found

    def _split(
        self, instruments: Sequence[str]
    ) -> tuple[dict[str, tuple[ScreenerHit, ...]], list[str]]:
        """(the hits held for ``instruments``, the instruments not held)."""
        out: dict[str, tuple[ScreenerHit, ...]] = {}
        missing: list[str] = []
        for iid in instruments:
            found = self._get(iid)
            if found is None:
                missing.append(iid)
            else:
                out[iid] = found
        return out, missing

    def _store(self, built: dict[str, tuple[ScreenerHit, ...]]) -> None:
        """Keep ``built`` (weighed outside the lock), evicting the oldest past the bound."""
        weights = {i: sum(weigh(h.result) + SLOT_BYTES for h in hits) for i, hits in built.items()}
        with self._lock:
            for iid, hits in built.items():
                self._bytes += weights[iid] - self._weights.get(iid, 0)
                self._hits[iid] = hits
                self._weights[iid] = weights[iid]
            while len(self._hits) > MAX_HELD_INSTRUMENTS:
                old, _ = self._hits.popitem(last=False)
                self._bytes -= self._weights.pop(old, 0)

    def get_or_build(
        self,
        instruments: Sequence[str],
        build: Callable[[Sequence[str]], dict[str, tuple[ScreenerHit, ...]]],
    ) -> tuple[dict[str, tuple[ScreenerHit, ...]], bool]:
        """The hits of ``instruments``; the ones not held are built together by ``build`` (one
        thread builds an instrument, the others wait for it); -> (hits, any built just now)."""
        out, missing = self._split(instruments)
        if not missing:
            return out, False
        with self._lock:
            flights = [self._flights.setdefault(i, Lock()) for i in sorted(missing)]
        for flight in flights:  # in one order: two callers never wait on each other
            flight.acquire()
        try:
            held, todo = self._split(missing)  # another thread may have built some meanwhile
            built = build(todo) if todo else {}
            self._store(built)
            out.update(held)
            out.update(built)
        finally:
            with self._lock:
                for iid, flight in zip(sorted(missing), flights, strict=True):
                    if self._flights.get(iid) is flight:  # not a newer caller's
                        del self._flights[iid]
            for flight in flights:
                flight.release()
        return out, bool(todo)

    def weight_bytes(self) -> int:
        with self._lock:
            return self._bytes


def load_screener_hits(
    ctx: ReadContext, instrument_ids: Sequence[str]
) -> dict[str, tuple[ScreenerHit, ...]]:
    """The hits of each of ``instrument_ids`` (by screener id; none: an empty tuple). The index of
    who picked what is built once per published state and caller; an instrument's results are read
    for it alone (from each picking run's own files), once, and kept."""
    index, key = _pick_index(ctx)
    held: HitsHeld = ctx.cache.get_or_compute((*key, "held"), HitsHeld)
    asked = list(dict.fromkeys(instrument_ids))
    found, grew = held.get_or_build(asked, lambda ids: _build(ctx, index, ids))
    if grew:
        ctx.cache.put((*key, "held"), held)  # its weight changed
    return {i: found[i] for i in asked}


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
        ctx.reader.version(),
        tuple(run.run_id for _, run in runs),
    )
    build: Callable[[], PickIndex] = lambda: _index(ctx, runs)  # noqa: E731
    found: PickIndex = ctx.cache.get_or_compute((*key, "index"), build)
    return found, key


def _index(ctx: ReadContext, runs: list[tuple[Screener, ScreenerRun]]) -> PickIndex:
    picked_by: dict[str, list[int]] = {}
    for n, (_, run) in enumerate(runs):
        rows = run_picks(ctx, run)  # the run's picks alone, read once (screen_picks by run id)
        for iid in rows["instrument_id"][picked_mask(rows["decision"])]:
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
    found = load_results(ctx, wanted, runs, changes, keep=False)  # ``HitsHeld`` is the cache
    out: dict[str, list[ScreenerHit]] = {i: [] for i in instruments}
    for iid in instruments:
        for n in index.picked_by.get(iid, ()):
            screener, run = index.runs[n]
            result = found.get((run.run_id, iid))
            if result is not None and is_picked(result.decision):
                out[iid].append(ScreenerHit(screener, result))
    return {i: tuple(hits) for i, hits in out.items()}
