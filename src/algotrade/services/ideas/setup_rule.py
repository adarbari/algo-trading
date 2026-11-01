"""The Ideas ranking rule over the picks of setups (ADR 0083 decision 2, "one ranking rule for
every viewer"): a pure function, no read and no clock. Evidence strength first (the setup's
verdict level, ``works`` before ``promising``, then its out-of-sample lift in points with a null
last, then its out-of-sample trades, then ``edge_id``), then the pick's place within the setup,
then ``instrument_id``. A ticker several setups picked is one idea at its best position and
lists the others (``also_in``). ``RULE_VERSION`` is recorded on every list."""

from collections.abc import Sequence
from dataclasses import dataclass

RULE_VERSION = 1
LEVEL_ORDER = {"works": 0, "promising": 1}


@dataclass(frozen=True)
class SetupStanding:
    """What the rule needs of a qualifying setup: its verdict ``level``, the out-of-sample
    ``lift_pts`` (None: not measured) and ``oos_trades`` (None: none counted)."""

    edge_id: str
    level: str
    lift_pts: float | None
    oos_trades: int | None


@dataclass(frozen=True)
class CandidatePick:
    """One setup's pick: ``place`` is its place among the setup's own picks (1 first)."""

    instrument_id: str
    setup: SetupStanding
    place: int


@dataclass(frozen=True)
class RankedIdea:
    """An idea: the ticker at its best pick, the other setups that picked it, its ``rank``."""

    rank: int
    instrument_id: str
    best: CandidatePick
    also_in: tuple[CandidatePick, ...]


def setup_key(s: SetupStanding) -> tuple[int, int, float, int, str]:
    """The order of setups: stronger evidence sorts first, a null lift or trade count last."""
    return (
        LEVEL_ORDER[s.level],
        1 if s.lift_pts is None else 0,
        0.0 if s.lift_pts is None else -s.lift_pts,
        -(s.oos_trades or 0),
        s.edge_id,
    )


def _pick_key(p: CandidatePick) -> tuple[tuple[int, int, float, int, str], int, str]:
    return setup_key(p.setup), p.place, p.instrument_id


def rank_picks(picks: Sequence[CandidatePick]) -> list[RankedIdea]:
    """One idea per ticker of ``picks``, best first, ranked from 1; ``also_in`` in the same
    order. A setup that picked a ticker twice counts once (its best place)."""
    by_ticker: dict[str, list[CandidatePick]] = {}
    for p in sorted(picks, key=_pick_key):
        found = by_ticker.setdefault(p.instrument_id, [])
        if all(q.setup.edge_id != p.setup.edge_id for q in found):
            found.append(p)
    ordered = sorted(by_ticker.values(), key=lambda found: _pick_key(found[0]))
    return [
        RankedIdea(i, found[0].instrument_id, found[0], tuple(found[1:]))
        for i, found in enumerate(ordered, start=1)
    ]
