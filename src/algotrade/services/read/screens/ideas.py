"""Ideas (ADR 0029) for one session: one row per ticker the viewer's screeners picked, ranked by
the pure rule of ``services/ideas/rule.py`` (owner decision 2026-10-22: a site screener's first 5
and the viewer's own first 20, a pick scoring weight / position, an idea its best pick's score;
parameters ``config/site/ranking/ideas.toml``). ``ideas.priority`` is retired: old preferences
that hold it are never read.

Each screener contributes its run for exactly ``ctx.session.date`` (``runs`` THE latest-run
rule); one with no run for it is listed ``NOT_RUN`` and picks nothing (no lookback), and one
whose rank follows values the viewer's licences do not cover (``run_withheld``) is listed
``withheld`` and contributes nothing, so its ranking is never listed. Its ``picked`` count is
over the whole run; its ``top`` are its first pool picks, built from the run's ``screen_picks``
rows and the reference snapshot alone (no ``rule_screen`` / values read). Per-ticker facts
(earnings, expiry, IV) are not here: the page asks ``Instrument.features(names)``.

An idea is served from its best pick only (no merging across picks): ``best`` with its stored
values, the regime and size multiplier it was stamped with, the display ``metrics`` and the
``watch_out`` ids; ``picked_by`` lists every pool pick of the ticker. A pick the regime gate held
back (``PAUSED``, ADR 0049) is no idea: it is listed apart in ``Ideas.paused`` (the same rule, one
entry per screener and ticker, the first ``limit``; ``paused_total`` counts every held run row)
with the stored reason.

Paged (owner decision 2026-10-22, docs/decisions/log.md "Ideas page size"): ``load_ideas`` returns
``limit`` ideas from the opaque ``after`` cursor (an offset into the one stable rank order,
stamped with a fingerprint of the session, the runs and the rule's hash: a cursor from another
state is refused, never a shifted page), ``next_cursor`` says where the next page starts. The
picks are ranked from each run's ``results/screen_picks`` file (a few columns of the picked rows,
never the run's every row); a run with no such file but picks (a run before the table) is ranked
from its ``rule_screen`` rows, never read as having no picks. Only the page's best picks (and the
screeners' first picks) have their stored values read. The paused section is the first page's."""

import base64
import binascii
import hashlib
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

import pandas as pd

from algotrade.config.ranking.ideas import IdeasRule, load_ideas_rule
from algotrade.config.user import SITE_USER
from algotrade.core.model.errors import ConfigurationError
from algotrade.services.ideas.rule import (
    NOT_RUN,
    RAN,
    WITHHELD,
    PausedPick,
    PoolPick,
    PoolRow,
    PoolRun,
    PoolStanding,
    pool_standing,
    rank_ideas,
    rank_paused,
)
from algotrade.services.read.context import ReadContext
from algotrade.services.read.instruments.catalogue import UnknownFeatureError
from algotrade.services.read.instruments.features import load_feature_values
from algotrade.services.read.instruments.identity import Instrument, load_instruments
from algotrade.services.read.screens.results import ScreenResult, load_results, run_withheld
from algotrade.services.read.screens.runs import (
    LatestRun,
    ScreenerRun,
    load_latest_runs,
    picked_mask,
    run_picks,
)
from algotrade.services.read.screens.screeners import Screener, load_screeners
from algotrade.services.read.values import Unknown, to_scalar
from algotrade.services.screening.rule_results import PAUSED

FIRST_PAGE = 50  # the page the Ideas page loads first and each "more" adds
LIQUIDITY_RISK = "LIQUIDITY_RISK"  # a decision (ADR 0054) that is also a watch-out id
WATCH_LIQUIDITY = "liquidity_risk"
WATCH_EARNINGS = "earnings_before_expiry"
EARNINGS_BEFORE_EXPIRY = "feature.earnings_before_expiry"  # the stored fact behind that watch-out


@dataclass(frozen=True)
class TopPick:
    """One of a screener's first pool picks: ``position`` in the run (1 is the first), the run's
    stored ``score`` for it (as ``ScreenResult.score``; None: stored none) and who it is in the
    session's reference snapshot (None: not in it)."""

    instrument_id: str
    instrument: Instrument | None
    position: int
    score: float | None


@dataclass(frozen=True)
class IdeaScreener:
    """One of the viewer's screeners on the Ideas page: its run for the session (or why none),
    how many tickers it picked over the whole run, whether the viewer's licences withhold it
    (it then contributes nothing) and its first pool picks (``top``)."""

    screener: Screener
    run: ScreenerRun | None
    not_run: Unknown | None
    picked: int
    top: tuple[TopPick, ...]
    withheld: bool = False


@dataclass(frozen=True)
class PickedBy:
    """One screener's pool pick of a ticker: its ``position`` in the run and ``score`` (weight
    over position, as a number to show; the order uses the exact fraction)."""

    config_id: str
    owner: str
    own: bool
    position: int
    score: float
    decision: str


@dataclass(frozen=True)
class IdeaMetric:
    """A stored display value of the best pick: a screener column or a criterion's value."""

    name: str
    value: float | str


@dataclass(frozen=True)
class Idea:
    """A ticker some screener picked, served from its ``best`` pick only. ``score``: that pick's
    (weight / position); ``picked_by``: every pool pick of the ticker, best first (its first is
    ``best``'s); ``regime`` / ``size_multiplier``: as ``best``'s run stamped them; ``metrics``:
    ``best``'s display values by name; ``watch_out``: ids of the reasons to look twice."""

    rank: int
    instrument_id: str
    instrument: Instrument | None
    score: float
    best: ScreenResult
    picked_by: tuple[PickedBy, ...]
    regime: str | None
    size_multiplier: float | None
    metrics: tuple[IdeaMetric, ...]
    watch_out: tuple[str, ...]


@dataclass(frozen=True)
class PausedIdea:
    """A ticker one screener picked and the regime gate held back: that screener's ``PAUSED``
    row (``result.reasons`` says why, ``result.regime`` the label)."""

    instrument_id: str
    instrument: Instrument | None
    result: ScreenResult


@dataclass(frozen=True)
class Ideas:
    """``screeners``: the viewer's screeners (their own first, then by id); ``total``: every
    ticker the rule listed (``items`` holds one page of it, ``next_cursor`` the next);
    ``paused_total``: every pick the gate held back (``paused`` holds the first ``limit`` of the
    rule's paused section); ``rule_hash``: the ranking rule's parameters' hash."""

    session: date
    screeners: tuple[IdeaScreener, ...]
    total: int
    items: tuple[Idea, ...]
    paused_total: int = 0
    paused: tuple[PausedIdea, ...] = ()
    next_cursor: str | None = None  # where the next page starts (None: this is the last)
    rule_hash: str = ""


def _pool(
    ctx: ReadContext,
    screeners: Sequence[Screener],
    latest: dict[tuple[str, str], LatestRun],
) -> tuple[list[PoolRun], dict[tuple[str, str], float | None]]:
    """One ``PoolRun`` per screener: its picked and paused rows in the run's rank order; a run
    withheld from the viewer is not read at all (its rows would leak a ranking). Also the stored
    score of every picked row by (run id, instrument id), for the screeners' ``top``."""
    pool = []
    scores: dict[tuple[str, str], float | None] = {}
    for s in screeners:
        found = latest[(s.owner, s.id)]
        own = s.owner != SITE_USER
        run = found.run
        if run is None:
            reason = found.not_run.public_reason if found.not_run is not None else None
            pool.append(PoolRun(s.owner, s.id, own, NOT_RUN, None, reason))
        elif run_withheld(ctx, run):
            pool.append(PoolRun(s.owner, s.id, own, WITHHELD, run.run_id))
        else:
            rows = run_picks(ctx, run)
            picked = rows[picked_mask(rows["decision"])]
            held = rows[rows["decision"].astype(str) == PAUSED]
            for iid, score in zip(picked["instrument_id"], picked["score"], strict=True):
                scores.setdefault((run.run_id, str(iid)), _score(score))
            pool.append(
                PoolRun(
                    s.owner,
                    s.id,
                    own,
                    RAN,
                    run.run_id,
                    None,
                    _rows(picked),
                    _rows(held),
                )
            )
    return pool, scores


def _score(value: object) -> float | None:
    found = to_scalar(value)
    return None if found is None else float(found)


def _rows(frame: pd.DataFrame) -> tuple[PoolRow, ...]:
    return tuple(
        PoolRow(str(i), str(d))
        for i, d in zip(frame["instrument_id"].tolist(), frame["decision"].tolist(), strict=True)
    )


def _fingerprint(session: date, pool: Sequence[PoolRun], rule: IdeasRule) -> str:
    """What a cursor is only good for: the session, the runs with their status (a withheld run
    is another pool) and the rule's parameters."""
    runs = sorted(f"{r.run_id}:{r.status}" for r in pool if r.run_id is not None)
    text = "|".join([session.isoformat(), *runs, "/", rule.hash])
    return hashlib.sha256(text.encode()).hexdigest()[:12]


def encode_cursor(fingerprint: str, offset: int) -> str:
    """The opaque cursor of the page starting at ``offset``."""
    return base64.urlsafe_b64encode(f"{fingerprint}:{offset}".encode()).decode().rstrip("=")


def decode_cursor(cursor: str | None, fingerprint: str) -> int:
    """The offset ``cursor`` names (0: none given). ``ConfigurationError`` for a cursor that is
    malformed or was made for another session, set of runs or rule (reload from the start)."""
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


def display_metrics(result: ScreenResult) -> tuple[IdeaMetric, ...]:
    """``result``'s display values by name: its criteria's values, then the screen's own
    columns (a column overrides a criterion of the same name); numbers and strings only."""
    found: dict[str, float | str] = {}
    for c in result.criteria:
        if isinstance(c.value, int | float | str) and not isinstance(c.value, bool):
            found[c.id] = c.value
    for column in result.columns:
        v = column.value
        if isinstance(v, int | float | str) and not isinstance(v, bool):
            found[column.name] = v
    return tuple(IdeaMetric(n, v) for n, v in found.items())


def _watch_out(best: ScreenResult, earnings_first: bool) -> tuple[str, ...]:
    ids = [*best.flags]
    if best.decision == LIQUIDITY_RISK:
        ids.append(WATCH_LIQUIDITY)
    if earnings_first:
        ids.append(WATCH_EARNINGS)
    return tuple(dict.fromkeys(ids))


def _earnings_first(ctx: ReadContext, ids: Sequence[str]) -> set[str]:
    """The tickers of ``ids`` whose stored fact says the earnings fall on or before the nearest
    expiry (one read for them all)."""
    if not ids:
        return set()
    try:
        found = load_feature_values(ctx, list(ids), [EARNINGS_BEFORE_EXPIRY])
    except UnknownFeatureError:  # a catalogue without the expression feature has no such fact
        return set()
    return {i for i, values in found.items() if values and values[0].value is True}


def _picked_by(picks: Sequence[PoolPick]) -> tuple[PickedBy, ...]:
    return tuple(
        PickedBy(p.config_id, p.owner, p.own, p.position, float(p.score), p.decision) for p in picks
    )


def _standing(
    s: PoolStanding,
    screener: Screener,
    found: LatestRun,
    scores: dict[tuple[str, str], float | None],
    instruments: dict[str, Instrument],
) -> IdeaScreener:
    run = found.run
    top = tuple(
        TopPick(p.instrument_id, instruments.get(p.instrument_id), p.position, scores[key])
        for p in s.top
        if (key := (p.run_id, p.instrument_id)) in scores
    )
    return IdeaScreener(
        screener, run, found.not_run, 0 if run is None else run.picked, top, s.status == WITHHELD
    )


def load_ideas(ctx: ReadContext, limit: int, after: str | None = None) -> Ideas:
    """``limit`` ideas of the viewer's screeners' runs for ``ctx.session``, best first, from the
    ``after`` cursor (none: the first page); ``Ideas.next_cursor`` is the next page's."""
    rule = load_ideas_rule(ctx.configs)
    screeners = load_screeners(ctx)
    latest = load_latest_runs(ctx, [(s.owner, s.id) for s in screeners])
    pool, scores = _pool(ctx, screeners, latest)
    stamp = _fingerprint(ctx.session.date, pool, rule)
    start = decode_cursor(after, stamp)
    ranked = rank_ideas(pool, rule)
    end = start + max(limit, 0)
    shown = ranked[start:end]
    standings = pool_standing(pool, rule)
    held: list[PausedPick] = rank_paused(pool, rule)[: max(limit, 0)] if start == 0 else []
    wanted: dict[str, list[str]] = {}
    for idea in shown:
        wanted.setdefault(idea.best.run_id, []).append(idea.instrument_id)
    for h in held:
        wanted.setdefault(h.pick.run_id, []).append(h.instrument_id)
    wanted = {run_id: list(dict.fromkeys(ids)) for run_id, ids in wanted.items()}  # each read once
    runs = [r for s in screeners if (r := latest[(s.owner, s.id)].run) is not None]
    results = load_results(ctx, wanted, runs)
    top_ids = sorted({p.instrument_id for st in standings for p in st.top})
    instruments = load_instruments(ctx, top_ids)
    early = _earnings_first(ctx, [i.instrument_id for i in shown])
    items = []
    for idea in shown:
        best = results[(idea.best.run_id, idea.instrument_id)]
        items.append(
            Idea(
                rank=idea.rank,
                instrument_id=idea.instrument_id,
                instrument=best.instrument,
                score=float(idea.score),
                best=best,
                picked_by=_picked_by(idea.picked_by),
                regime=best.regime,
                size_multiplier=best.size_multiplier,
                metrics=display_metrics(best),
                watch_out=_watch_out(best, idea.instrument_id in early),
            )
        )
    paused = tuple(
        PausedIdea(h.instrument_id, row.instrument, row)
        for h in held
        if (row := results.get((h.pick.run_id, h.instrument_id))) is not None
    )
    by_key = {(s.owner, s.id): s for s in screeners}
    listed = tuple(
        _standing(
            st,
            by_key[(st.owner, st.config_id)],
            latest[(st.owner, st.config_id)],
            scores,
            instruments,
        )
        for st in standings
    )
    read = {p.run_id for p in pool if p.status == RAN}  # a withheld run's held rows are not counted
    paused_total = sum(r.paused for r in runs if r.run_id in read)
    more = encode_cursor(stamp, end) if end < len(ranked) and shown else None
    return Ideas(
        ctx.session.date, listed, len(ranked), tuple(items), paused_total, paused, more, rule.hash
    )
