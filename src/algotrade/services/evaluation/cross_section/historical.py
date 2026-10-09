"""A session before the first reference snapshot, as the harness reads it (ADR 0053 amendment
2026-10-09): the names are the listing history's alive on the session (``data.listings.identity``),
and a run that touched one says so. Two things live here.

``require_liquidity_rule``: a delisted name has no ``optionable`` flag, so the universe's own
close and ``adv_usd_20d`` thresholds decide in its place; a universe that reads ``optionable``
without both has no threshold to use and the run stops (``ConfigurationError``), never a number
of our own.

``IdentityTally`` / ``HistoricalCaveat``: the rule and, per path (today's flag, liquidity
proxy), how many eligible and screened names it covered over the sessions, persisted with the run
and shown in its report. Every number over those sessions carries the lookahead tilt of
today's flag: it favours names that later grew into optionable ones."""

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date

from algotrade.config.strategy.schema import Selection
from algotrade.core.model.errors import ConfigurationError
from algotrade.data.listings.identity import PROXY, RULE, TODAY_FLAG

OPTIONABLE = "instrument.optionable"
PRICE = re.compile(r"^rollup\.price_stats@v\d+\.close$")
VOLUME = re.compile(r"^rollup\.price_stats@v\d+\.adv_usd_20d$")
FLOORS = ("gt", "gte")


def require_liquidity_rule(selection: Selection) -> None:
    """Raise when ``selection`` reads ``optionable`` but declares no price and no dollar-volume
    floor for the names that have none (a delisted name's proxy)."""
    rules = selection.where.rules()
    if not any(r.field == OPTIONABLE for r in rules):
        return
    floors = {r.field for r in rules if r.op in FLOORS}
    if not (any(PRICE.match(f) for f in floors) and any(VOLUME.match(f) for f in floors)):
        raise ConfigurationError(
            f"selection {selection.name!r} reads instrument.optionable but has no close and "
            "adv_usd_20d floor: a session before the first reference snapshot has no flag for "
            "a delisted name and the universe gives no liquidity threshold to use instead"
        )


@dataclass(frozen=True)
class HistoricalCaveat:
    """What the run read for sessions before the first reference snapshot: ``sessions`` of them,
    the names ``eligible`` and ``screened`` there by path (today's flag, proxy)."""

    rule: str
    sessions: int
    eligible: Mapping[str, int]
    screened: Mapping[str, int]

    def as_dict(self) -> dict[str, object]:
        return {
            "rule": self.rule,
            "sessions": self.sessions,
            "eligible": dict(self.eligible),
            "screened": dict(self.screened),
        }


class IdentityTally:
    """The paths each session's names took, noted once per (kind, session) as they are read."""

    def __init__(self) -> None:
        self._seen: dict[tuple[str, date], Mapping[str, int]] = {}

    def note(self, kind: str, day: date, paths: Mapping[str, int]) -> None:
        if paths:
            self._seen.setdefault((kind, day), paths)

    def caveat(self) -> HistoricalCaveat | None:
        if not self._seen:
            return None

        def total(kind: str) -> dict[str, int]:
            rows = [p for (k, _), p in self._seen.items() if k == kind]
            return {path: sum(p.get(path, 0) for p in rows) for path in (TODAY_FLAG, PROXY)}

        return HistoricalCaveat(
            RULE, len({d for _, d in self._seen}), total("eligible"), total("screened")
        )
