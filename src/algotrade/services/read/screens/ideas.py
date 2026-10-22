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
and never hide it. An idea's ``regime`` and ``size_multiplier`` are those of its best pick.

Paged (owner decision 2026-10-22, docs/decisions/log.md "Ideas page size"): ``load_ideas`` returns
``limit`` ideas from the opaque ``after`` cursor (an offset into the one stable rank order of the
session's runs, stamped with a fingerprint of the session, the runs and the priority: a cursor
from another state is refused, never a shifted page), ``next_cursor`` says where the next page
starts. The picks are ranked from each run's ``results/screen_picks`` file (a few columns of the
picked rows, never the run's every row); a run with no such file but picks (a run before the
table) is ranked from its ``rule_screen`` rows, never read as having no picks. The paused
section is the first page's."""

import base64
import binascii
import hashlib
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any

import pandas as pd

from algotrade.core.model.errors import ConfigurationError
from algotrade.services.read.context import ReadContext
from algotrade.services.read.instruments.identity import Instrument
from algotrade.services.read.screens.results import ScreenResult, load_results, run_withheld
from algotrade.services.read.screens.runs import (
    ScreenerRun,
    load_latest_runs,
    picked_mask,
    run_picks,
)
from algotrade.services.read.screens.screeners import Screener, load_screeners
from algotrade.services.read.values import Unknown, to_scalar
from algotrade.services.screening.rule_results import PAUSED

PREFERENCES = "preferences"
TOP_PER_SCREENER = 3
FIRST_PAGE = 50  # the page the Ideas page loads first and each "more" adds


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
    every ticker picked (``items`` holds one page of it, ``next_cursor`` the next);
    ``paused_total``: every pick the gate held back (``paused`` holds the first ``limit``)."""

    session: date
    priority: tuple[str, ...]
    screeners: tuple[IdeaScreener, ...]
    total: int
    items: tuple[Idea, ...]
    paused_total: int = 0
    paused: tuple[PausedIdea, ...] = ()
    next_cursor: str | None = None  # where the next page starts (None: this is the last)


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
) -> tuple[dict[str, list[tuple[Any, str]]], dict[str, pd.DataFrame]]:
    """(``{instrument id: [(sort key, run id)]}`` of every pick, best first: the screener's
    place in ``priority`` (unlisted ones share the last place), then score, then the run's own
    rank (which holds its tie-break), then the screener's id; each run's picked and paused
    rows by run id)."""
    place = {c: n for n, c in enumerate(priority)}
    out: dict[str, list[tuple[Any, str]]] = {}
    held: dict[str, pd.DataFrame] = {}
    for run in runs:
        rows = held[run.run_id] = run_picks(ctx, run)
        picked = rows[picked_mask(rows["decision"])]
        hidden = bool(run_withheld(ctx, run))  # a screen seen by names only: no order by values
        for iid, score, rank in zip(
            picked["instrument_id"].tolist(),
            picked["score"].tolist(),
            picked["rank"].tolist(),
            strict=True,
        ):
            key = (
                place.get(run.config_id, len(place)),
                1.0 if hidden else -_or(score, -1.0),
                0 if hidden else int(rank),
                run.config_id,
            )
            out.setdefault(str(iid), []).append((key, run.run_id))
    for found in out.values():
        found.sort()
    return out, held


def _top(rows: pd.DataFrame) -> list[str]:
    picked = rows[picked_mask(rows["decision"])]
    return [str(i) for i in picked["instrument_id"].head(TOP_PER_SCREENER)]


def _paused(
    runs: Sequence[ScreenerRun], held: dict[str, pd.DataFrame], limit: int
) -> list[tuple[str, str]]:
    """``(run id, instrument id)`` of the first ``limit`` PAUSED rows, runs in the order given
    (the user's priority), each in rank order."""
    out: list[tuple[str, str]] = []
    for run in runs:
        rows = held[run.run_id]
        out.extend(
            (run.run_id, str(i))
            for i in rows[rows["decision"].astype(str) == PAUSED]["instrument_id"]
        )
    return out[: max(limit, 0)]


def _fingerprint(session: date, runs: Sequence[ScreenerRun], priority: Sequence[str]) -> str:
    """What a cursor is only good for: the session, the runs read and the priority."""
    text = "|".join([session.isoformat(), *(r.run_id for r in runs), "/", *priority])
    return hashlib.sha256(text.encode()).hexdigest()[:12]


def encode_cursor(fingerprint: str, offset: int) -> str:
    """The opaque cursor of the page starting at ``offset``."""
    return base64.urlsafe_b64encode(f"{fingerprint}:{offset}".encode()).decode().rstrip("=")


def decode_cursor(cursor: str | None, fingerprint: str) -> int:
    """The offset ``cursor`` names (0: none given). ``ConfigurationError`` for a cursor that is
    malformed or was made for another session, set of runs or priority (reload from the start)."""
    if not cursor:
        return 0
    try:
        text = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)).decode()
        stamp, _, offset = text.rpartition(":")
        found = int(offset)
    except (binascii.Error, ValueError) as error:
        raise ConfigurationError("after: not a cursor this API issued") from error
    if found < 0:
        raise ConfigurationError("after: not a cursor this API issued")
    if stamp != fingerprint:
        raise ConfigurationError("after: the ideas changed since this cursor was issued; reload")
    return found


def load_ideas(ctx: ReadContext, limit: int, after: str | None = None) -> Ideas:
    """``limit`` tickers of the user's screeners' runs for ``ctx.session``, best first, from
    the ``after`` cursor (none: the first page); ``Ideas.next_cursor`` is the next page's."""
    priority = screener_priority(ctx)
    screeners = _ordered(load_screeners(ctx), priority)
    latest = load_latest_runs(ctx, [(s.owner, s.id) for s in screeners])
    runs = [r for s in screeners if (r := latest[(s.owner, s.id)].run) is not None]
    stamp = _fingerprint(ctx.session.date, runs, priority)
    start = decode_cursor(after, stamp)
    candidates, rows = _picks(ctx, runs, priority)
    ranked = sorted(candidates, key=lambda i: (candidates[i][0][0], i))
    end = start + max(limit, 0)
    shown = ranked[start:end]
    tops = {r.run_id: _top(rows[r.run_id]) for r in runs}
    wanted: dict[str, list[str]] = {r.run_id: list(tops[r.run_id]) for r in runs}
    for iid in shown:
        for _, run_id in candidates[iid]:
            wanted[run_id].append(iid)
    held = _paused(runs, rows, limit) if start == 0 else []  # the paused section is page one's
    for run_id, iid in held:
        wanted[run_id].append(iid)
    wanted = {run_id: list(dict.fromkeys(ids)) for run_id, ids in wanted.items()}  # each read once
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
        for n, iid in enumerate(shown, start=start + 1)
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
    more = encode_cursor(stamp, end) if end < len(ranked) and shown else None
    return Ideas(
        ctx.session.date, priority, tuple(listed), len(ranked), items, paused_total, paused, more
    )
