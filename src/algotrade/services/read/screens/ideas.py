"""Ideas (ADR 0029) for one session: one row per ticker any of the user's screeners picked,
listing every screener that picked it, ranked by the user's screener priority
(``preferences.toml`` ``ideas.priority``), then score, the tie-break and instrument id.

Each screener contributes its run for exactly ``ctx.session.date`` (``runs`` THE latest-run
rule); one with no run for it is listed ``NOT_RUN`` and picks nothing (no lookback). Its
``picked`` count and best picks are over the whole run, not over the rows shown. Per-ticker
facts (earnings, expiry, IV) are not here: the page asks ``Instrument.features(names)``.

A pick the regime gate held back (``PAUSED``, ADR 0049) is no idea: it is listed apart in
``Ideas.paused`` (one entry per screener and ticker, screener priority then rank, the first
``limit``; ``paused_total`` counts them all) with the stored reason, so the page can show it
and never hide it. An idea's ``regime`` and ``size_multiplier`` are those of its best pick."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any

from algotrade.services.read.context import ReadContext
from algotrade.services.read.instruments.identity import Instrument
from algotrade.services.read.screens.results import ScreenResult, load_results
from algotrade.services.read.screens.runs import (
    PAUSED,
    ScreenerRun,
    is_picked,
    load_latest_runs,
    run_rows,
)
from algotrade.services.read.screens.screeners import Screener, load_screeners
from algotrade.services.read.values import Unknown, to_scalar

PREFERENCES = "preferences"
TOP_PER_SCREENER = 3


@dataclass(frozen=True)
class IdeaScreener:
    """One of the user's screeners on the Ideas page: its run for the session (or why none),
    how many tickers it picked and its best picks (by rank), both over the whole run."""

    screener: Screener
    run: ScreenerRun | None
    not_run: Unknown | None
    picked: int
    top: tuple[ScreenResult, ...]


@dataclass(frozen=True)
class Idea:
    """A ticker some screener picked: ``picks``, highest-priority screener first."""

    rank: int
    instrument_id: str
    instrument: Instrument | None
    picks: tuple[ScreenResult, ...]
    regime: str | None
    size_multiplier: float | None


@dataclass(frozen=True)
class PausedIdea:
    """A ticker one screener picked and the regime gate held back: that screener's ``PAUSED``
    row (``result.reasons`` says why, ``result.regime`` the label)."""

    instrument_id: str
    instrument: Instrument | None
    result: ScreenResult


@dataclass(frozen=True)
class Ideas:
    """``screeners``: the user's screeners in priority order, then the rest by id; ``total``:
    every ticker picked (``items`` holds the first ``limit``); ``paused_total``: every pick the
    gate held back (``paused`` holds the first ``limit``)."""

    session: date
    priority: tuple[str, ...]
    screeners: tuple[IdeaScreener, ...]
    total: int
    items: tuple[Idea, ...]
    paused_total: int = 0
    paused: tuple[PausedIdea, ...] = ()


def screener_priority(ctx: ReadContext) -> tuple[str, ...]:
    """``ideas.priority`` of the user's ``preferences.toml`` (screener ids, best first)."""
    doc = ctx.configs.load(ctx.user.user_id, PREFERENCES, PREFERENCES) or {}
    found = (doc.get("ideas") or {}).get("priority") or []
    return tuple(dict.fromkeys(str(i) for i in found))


def _ordered(screeners: Sequence[Screener], priority: Sequence[str]) -> list[Screener]:
    by_id = {s.id: s for s in screeners}
    listed = [by_id[i] for i in priority if i in by_id]
    return listed + [s for s in screeners if s.id not in priority]


def _or(value: object, missing: float) -> float:
    found = to_scalar(value)
    return missing if found is None else float(found)


def _picks(
    ctx: ReadContext, runs: Sequence[ScreenerRun], priority: Sequence[str]
) -> dict[str, list[tuple[Any, str]]]:
    """``{instrument id: [(sort key, run id)]}`` of every pick, best first: the screener's
    place in ``priority`` (unlisted ones share the last place), then score, then the
    tie-break (missing ones last), then the screener's id."""
    place = {c: n for n, c in enumerate(priority)}
    out: dict[str, list[tuple[Any, str]]] = {}
    for run in runs:
        rows = run_rows(ctx, run)
        for iid, decision, score, tie in zip(
            rows["instrument_id"], rows["decision"], rows["score"], rows["tie_break"], strict=True
        ):
            if not is_picked(str(decision)):
                continue
            key = (
                place.get(run.config_id, len(place)),
                -_or(score, -1.0),
                -_or(tie, float("-inf")),
                run.config_id,
            )
            out.setdefault(str(iid), []).append((key, run.run_id))
    for found in out.values():
        found.sort()
    return out


def _top(ctx: ReadContext, run: ScreenerRun) -> list[str]:
    rows = run_rows(ctx, run)
    picked = rows[[is_picked(str(d)) for d in rows["decision"]]]
    return [str(i) for i in picked["instrument_id"].head(TOP_PER_SCREENER)]


def _paused(ctx: ReadContext, runs: Sequence[ScreenerRun], limit: int) -> list[tuple[str, str]]:
    """``(run id, instrument id)`` of the first ``limit`` PAUSED rows, runs in the order given
    (the user's priority), each in rank order."""
    out: list[tuple[str, str]] = []
    for run in runs:
        rows = run_rows(ctx, run)
        held = rows[rows["decision"].astype(str) == PAUSED]
        out.extend((run.run_id, str(i)) for i in held["instrument_id"])
    return out[: max(limit, 0)]


def load_ideas(ctx: ReadContext, limit: int) -> Ideas:
    """The ``limit`` best tickers over the user's screeners' runs for ``ctx.session``."""
    priority = screener_priority(ctx)
    screeners = _ordered(load_screeners(ctx), priority)
    latest = load_latest_runs(ctx, [(s.owner, s.id) for s in screeners])
    runs = [r for s in screeners if (r := latest[(s.owner, s.id)].run) is not None]
    candidates = _picks(ctx, runs, priority)
    ranked = sorted(candidates, key=lambda i: (candidates[i][0][0], i))
    shown = ranked[: max(limit, 0)]
    tops = {r.run_id: _top(ctx, r) for r in runs}
    wanted: dict[str, list[str]] = {r.run_id: list(tops[r.run_id]) for r in runs}
    for iid in shown:
        for _, run_id in candidates[iid]:
            wanted[run_id].append(iid)
    held = _paused(ctx, runs, limit)
    for run_id, iid in held:
        wanted[run_id].append(iid)
    results = load_results(ctx, wanted, runs)
    items = tuple(
        Idea(
            rank=n,
            instrument_id=iid,
            instrument=(best := results[(candidates[iid][0][1], iid)]).instrument,
            picks=tuple(results[(run_id, iid)] for _, run_id in candidates[iid]),
            regime=best.regime,
            size_multiplier=best.size_multiplier,
        )
        for n, iid in enumerate(shown, start=1)
    )
    paused = tuple(
        PausedIdea(iid, results[(run_id, iid)].instrument, results[(run_id, iid)])
        for run_id, iid in held
    )
    listed = []
    for s in screeners:
        found = latest[(s.owner, s.id)]
        run = found.run
        top = () if run is None else tuple(results[(run.run_id, i)] for i in tops[run.run_id])
        listed.append(IdeaScreener(s, run, found.not_run, 0 if run is None else run.picked, top))
    paused_total = sum(r.paused for r in runs)
    return Ideas(
        ctx.session.date, priority, tuple(listed), len(ranked), items, paused_total, paused
    )
