"""How long a ticker has stayed on a screener's pick list (``days_picked``) and whether it is new
to it (``new_today``): read-time facts over a run and the chain of previous runs it names, for the
filter of the screener-results surface (ADR 0082; Ideas waits for the streaks to be precomputed
at ingestion, decided 2026-10-24).

``days_picked`` of a ticker the run picks is 1 plus the consecutive earlier runs of the screener
that also picked it (``runs.load_previous_run``: each run's previous run, never the screener's
latest), counted from the picked rows of each run's ``screen_picks`` file; the walk stops at the
first run that did not pick it, and at ``CAP`` (a streak of 20 or more is 20: the filter's last
bin). A ticker the run did not pick has 0. The value is UNKNOWN (None, never 0 or a short streak)
when the walk, before the streak ended, reaches a run withheld from the viewer (its picks follow
values the viewer's licences do not cover) or the end of the chain (no previous run: the screener
did not run in the previous stored session, or never ran before; a first run is not taken for a
streak of one). Nothing looks forward: a run's value is the same however many later runs exist.

``new_today`` is the one-step form: True when the previous run did not pick the ticker, False when
it did, None when there is no previous run or it is withheld. Both are cached per run, viewer's
licences and published state (ADR 0022). Whether a run is withheld is the caller's ``withheld``
(``results.run_withheld``, which this module cannot import: it reads streaks)."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from typing import Final

from algotrade.services.read.context import ReadContext, at_session
from algotrade.services.read.filtering.definitions import ResolvedFilters
from algotrade.services.read.filtering.masks import FilterInput
from algotrade.services.read.screens.runs import (
    ScreenerRun,
    load_previous_run,
    picked_mask,
    run_picks,
)

HISTORY: Final = frozenset({"days_picked", "new_today"})  # the filter columns read from this walk
CAP: Final = 20  # a streak this long or longer is reported as this (the filter's last bin)

Withheld = Callable[[ReadContext, ScreenerRun], object]  # truthy: the viewer may not see the run


def history_wanted(resolved: ResolvedFilters, inputs: Sequence[FilterInput]) -> frozenset[str]:
    """The history columns (``HISTORY``) a request needs: those of the offered filters the viewer
    has set active. The walk is read for these alone: a request without them never walks."""
    active = {i.id for i in inputs if i.active}
    return frozenset(
        f.column_id for f in resolved.offered if f.id in active and f.column_id in HISTORY
    )


def without_idle(resolved: ResolvedFilters, wanted: frozenset[str]) -> ResolvedFilters:
    """``resolved`` without the history filters ``wanted`` does not name: their facets are not
    served until the filter is set (counting them would need the walk on every request)."""
    kept = tuple(f for f in resolved.offered if f.column_id not in HISTORY or f.column_id in wanted)
    return replace(resolved, offered=kept)


@dataclass(frozen=True)
class Previous:
    """The step back from a run: the run before it with the context of its session and the
    tickers it picked."""

    ctx: ReadContext
    run: ScreenerRun
    picked: frozenset[str]


def picked_ids(ctx: ReadContext, run: ScreenerRun) -> frozenset[str]:
    """The instrument ids ``run`` picked (a PAUSED row is not a pick)."""
    rows = run_picks(ctx, run)
    return frozenset(str(i) for i in rows.loc[picked_mask(rows["decision"]), "instrument_id"])


def previous_of(ctx: ReadContext, run: ScreenerRun, withheld: Withheld) -> Previous | None:
    """The run before ``run`` with what it picked; None: there is none, or the viewer may not see
    it (the caller cannot tell which, and treats both as not known)."""
    before = load_previous_run(ctx, run)
    if before is None:
        return None
    there = at_session(ctx, before.session)
    if withheld(there, before):
        return None
    return Previous(there, before, picked_ids(there, before))


def _key(name: str, ctx: ReadContext, run: ScreenerRun) -> tuple[object, ...]:
    return (name, run.run_id, ctx.session.date, ctx.reader.own_run, ctx.reader.version(),
            ctx.user.user_id, tuple(sorted(ctx.licences)))  # fmt: skip


def new_today(ctx: ReadContext, run: ScreenerRun, withheld: Withheld) -> dict[str, bool | None]:
    """For each ticker ``run`` picked: True when its previous run did not pick it, False when it
    did, None for all when there is no previous run or it is withheld, or ``run`` itself is
    withheld."""
    key = _key("streak_new_today", ctx, run)
    found: dict[str, bool | None] | None = ctx.cache.get(key)
    if found is None:
        now = picked_ids(ctx, run)
        step = None if withheld(ctx, run) else previous_of(ctx, run, withheld)
        found = {i: None if step is None else i not in step.picked for i in now}
        ctx.cache.put(key, found)
    return found


def days_picked(ctx: ReadContext, run: ScreenerRun, withheld: Withheld) -> dict[str, int | None]:
    """For each ticker ``run`` picked: how many runs in a row, ending with ``run``, picked it
    (``CAP`` at most), or None when that cannot be said (see the module docstring). A ticker
    ``run`` did not pick is not in the result (its streak is 0)."""
    key = _key("streak_days_picked", ctx, run)
    found: dict[str, int | None] | None = ctx.cache.get(key)
    if found is None:
        found = _walk(ctx, run, withheld)
        ctx.cache.put(key, found)
    return found


def _walk(ctx: ReadContext, run: ScreenerRun, withheld: Withheld) -> dict[str, int | None]:
    now = picked_ids(ctx, run)
    if withheld(ctx, run):
        return dict.fromkeys(now)
    alive = dict.fromkeys(now, 1)  # still on the list at the run reached: its streak so far
    out: dict[str, int | None] = {}
    here, current = ctx, run
    for _ in range(CAP - 1):  # every live ticker has the same count: one step back each
        if not alive:
            break
        step = previous_of(here, current, withheld)
        if step is None:  # the chain ends (or is hidden) before these streaks do
            out.update(dict.fromkeys(alive))
            return out
        for i in list(alive):
            if i in step.picked:
                alive[i] += 1
            else:
                out[i] = alive.pop(i)
        here, current = step.ctx, step.run
    out.update(alive)
    return out
