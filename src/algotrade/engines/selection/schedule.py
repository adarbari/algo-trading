"""When a backtest re-evaluates its selection, and what each re-evaluation changed (pure).

``[backtest] rebalance_selection`` (validated by ``config.site.settings``) is interpreted here:

- ``none``:    one evaluation, on the backtest's ``start`` (the behaviour before rebalancing)
- ``monthly``: ``start``, then the first session of every later calendar month
- ``weekly``:  ``start``, then the first session of every later ISO week
- ``<N>d``:    ``start``, then every ``N``-th session after it (sessions, not calendar days)

Evaluating the selection is ``services.selection.select`` (point in time, per session); this
module only picks the sessions and audits the difference between consecutive selections.
"""

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from itertools import pairwise
from typing import Any

from algotrade.core.model.errors import ConfigurationError
from algotrade.engines.selection.evaluate import SelectionResult

LISTED = 25  # added / removed ids are listed up to this many; beyond, counts + the hash


def rebalance_sessions(start: date, sessions: Sequence[date], frequency: str) -> list[date]:
    """``start`` plus the sessions (ascending, after ``start``) that re-evaluate the selection."""
    later = [s for s in sessions if s > start]
    if frequency == "none":
        picked: list[date] = []
    elif frequency == "monthly":
        picked = _firsts(start, later, lambda d: (d.year, d.month))
    elif frequency == "weekly":
        picked = _firsts(start, later, lambda d: d.isocalendar()[:2])
    elif frequency.endswith("d") and frequency[:-1].isdigit() and int(frequency[:-1]) > 0:
        step = int(frequency[:-1])
        picked = later[step - 1 :: step]
    else:
        raise ConfigurationError(f"unknown rebalance_selection {frequency!r}")
    return [start, *picked]


def _firsts(start: date, sessions: Sequence[date], period: Any) -> list[date]:
    """The first session of every period after the one ``start`` is in."""
    out: list[date] = []
    seen = period(start)
    for session in sessions:
        if period(session) != seen:
            seen = period(session)
            out.append(session)
    return out


def members_hash(instruments: Sequence[str]) -> str:
    """A short, order-independent fingerprint of a selected set (for audits)."""
    text = "\n".join(sorted(instruments))
    return hashlib.sha256(text.encode()).hexdigest()[:16]


@dataclass(frozen=True)
class Rebalance:
    """One evaluation of the selection: when, what it chose, and what changed."""

    evaluated: date  # the session whose data the selection read
    effective: date | None  # first bar trading with this set (None: after the last bar)
    selection: SelectionResult
    added: tuple[str, ...]
    removed: tuple[str, ...]
    survivorship_bias: bool  # the reference snapshot is after ``evaluated``

    @property
    def members(self) -> frozenset[str]:
        return frozenset(self.selection.instruments)

    def as_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "evaluated": self.evaluated.isoformat(),
            "effective": self.effective.isoformat() if self.effective else None,
            "selected": len(self.selection.instruments),
            "members_hash": members_hash(self.selection.instruments),
            "added_count": len(self.added),
            "removed_count": len(self.removed),
            "survivorship_bias": self.survivorship_bias,
            "funnel": self.selection.as_dict(),
        }
        if len(self.added) <= LISTED:
            out["added"] = list(self.added)
        if len(self.removed) <= LISTED:
            out["removed"] = list(self.removed)
        return out


def diff(
    previous: frozenset[str], selected: SelectionResult
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """(added, removed) instrument ids, sorted."""
    now = frozenset(selected.instruments)
    return tuple(sorted(now - previous)), tuple(sorted(previous - now))


def turnover(rebalances: Sequence[Rebalance]) -> float:
    """Mean share of the set replaced per re-evaluation (added / previous size); 0 if none."""
    shares = [
        len(r.added) / len(prev.selection.instruments)
        for prev, r in pairwise(rebalances)
        if prev.selection.instruments and r.effective is not None
    ]
    return sum(shares) / len(shares) if shares else 0.0
