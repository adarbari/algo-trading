"""The reference episodes and NBER recessions a market-regime page draws (ADR 0047), from
``config/site/regime/episodes.toml``, known as of ``ctx.session`` and no later (point in time:
a page for an old session never shows what only a later one could know).

- An episode is listed from its ``known_from`` (its trough: the depth is not known before the
  episode ended); its ``recovered`` date is shown only once that session has come (``None``
  before: "not recovered yet" is what the session knew). What it says about a recession is
  gated by the matching recession's announcements: ``recession`` / ``nber_start`` and ``kind``
  (``shock`` until then) only from the day NBER announced the peak, ``nber_end`` only from the
  day it announced the trough (so a trough listed in March 2020 is not yet "a recession").
- A recession is listed from ``announced_start`` (the day the NBER committee dated its peak;
  ``start`` where NBER published none) and its ``end`` is shown only from ``announced_end``
  (``end`` where none): before that the recession is ongoing as far as the session knew.
  The announcement dates themselves are shown only once they are past.

Episodes and recessions in file order (oldest first), so a page lists them as the site
reviewed them."""

from dataclasses import dataclass
from datetime import date

from algotrade.config.site.regime.episodes import Episode as EpisodeConfig
from algotrade.config.site.regime.episodes import Recession as RecessionConfig
from algotrade.config.site.regime.episodes import load_episodes
from algotrade.services.read.context import ReadContext


@dataclass(frozen=True)
class Episode:
    """One reference drawdown. ``recovered``: the session the S&P 500 regained its peak
    (``None``: not yet, as of the session); ``nber_start`` / ``nber_end`` as the config's."""

    key: str
    name: str
    kind: str
    peak: date
    trough: date
    recovered: date | None
    spx_drawdown: float
    nasdaq_drawdown: float
    recession: bool
    nber_start: date | None
    nber_end: date | None
    cause: str
    notes: str
    known_from: date


@dataclass(frozen=True)
class Recession:
    """One NBER recession as ``ctx.session`` knew it: ``end`` is ``None`` while it was not yet
    dated over; the announcement dates are ``None`` where none was published or it is not
    past."""

    start: date
    end: date | None
    announced_start: date | None
    announced_end: date | None


@dataclass(frozen=True)
class RegimeEpisodes:
    """What the session knows of the reference episodes and recessions."""

    episodes: tuple[Episode, ...]
    recessions: tuple[Recession, ...]


def _known(r: RecessionConfig, day: date) -> tuple[bool, bool]:
    """``(peak announced, trough announced)`` by ``day`` (the month itself where none)."""
    return (r.announced_start or r.start) <= day, (r.announced_end or r.end) <= day


def episode_known_by(
    e: EpisodeConfig, day: date, chronology: tuple[RecessionConfig, ...]
) -> Episode:
    """``e`` as of ``day``: the recession and the recovery only once known (the one mapping;
    the Guide passes ``date.max`` for the whole record)."""
    started = ended = True  # an episode with no recession: nothing to gate
    if e.recession:
        match = next(
            (r for r in chronology if (r.start, r.end) == (e.nber_start, e.nber_end)), None
        )
        started, ended = _known(match, day) if match else (True, True)
    return Episode(
        key=e.key,
        name=e.name,
        kind=e.kind if started else "shock",
        peak=e.peak,
        trough=e.trough,
        recovered=e.recovered if e.recovered is not None and e.recovered <= day else None,
        spx_drawdown=e.spx_drawdown,
        nasdaq_drawdown=e.nasdaq_drawdown,
        recession=e.recession and started,
        nber_start=e.nber_start if started else None,
        nber_end=e.nber_end if started and ended else None,
        cause=e.cause,
        notes=e.notes,
        known_from=e.known_from,
    )


def _recession(r: RecessionConfig, day: date) -> Recession | None:
    if (r.announced_start or r.start) > day:
        return None
    ended = _known(r, day)[1]
    return Recession(
        start=r.start,
        end=r.end if ended else None,
        announced_start=r.announced_start,
        announced_end=r.announced_end if ended else None,
    )


def load_regime_episodes(ctx: ReadContext) -> RegimeEpisodes:
    """The episodes and recessions ``ctx.session`` knows (none without the config)."""
    day = ctx.session.date
    config = load_episodes(ctx.configs)
    return RegimeEpisodes(
        episodes=tuple(
            episode_known_by(e, day, config.recessions)
            for e in config.episodes
            if e.known_from <= day
        ),
        recessions=tuple(r for c in config.recessions if (r := _recession(c, day)) is not None),
    )
