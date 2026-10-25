"""``KnownCoverage``: for the session, how many values of the fundamentals share count are KNOWN
against the rows stored, per security type, and why an operating company has none (Admin
Ingestion, owner decision 2026-10-24: the completeness grid counts rows, and fundamentals has a
row for every name with a null count for an ETF, so it read green at 47% known).

It reads run records only: the ``breakdown`` of the ``coverage_fundamentals.shares_outstanding``
check the nightly's ``rollups`` step stored (``tasks/maintenance/coverage.py``,
``known_breakdown``; the newest record of exactly ``ctx.session.date`` that holds it), never a
partition and never an earlier session. A session whose records carry none is ``unknown``
NOT_RUN with its run cause, never 0%. The causes (``KnownGap``) name where a gap came from
(a CIK, a facts fetch), so the whole read is admin-only at the graph (ADR 0056); each has a Guide
term."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from typing import Any

from algotrade.services.read.availability.cause import run_cause
from algotrade.services.read.availability.data_status import FUNDAMENTALS_FEATURE, check_data
from algotrade.services.read.context import ReadContext
from algotrade.services.read.session import NIGHTLY
from algotrade.services.read.values import Unknown, UnknownCode

__all__ = ["KnownByType", "KnownCoverage", "KnownGap", "KnownGapCount", "load_known_coverage"]

BREAKDOWN = "breakdown"  # the key of the check's data


class KnownGap(StrEnum):
    """Why an operating company has no value (the ingestion's ``KNOWN_CAUSES``)."""

    BLANK_CHECK = "BLANK_CHECK"  # a SPAC (SIC 6770): no shares data by design
    NO_CIK = "NO_CIK"  # no company CIK to fetch facts for
    NO_FACTS = "NO_FACTS"  # a row stored, but the facts carry no count (no dei / weighted_basic)
    NO_ROW = "NO_ROW"  # nothing stored for the name


@dataclass(frozen=True)
class KnownByType:
    """One security type: ``names`` of the universe, ``rows`` stored of them, ``known`` values
    and their ``share`` of the names (None for a type with no names): the figure the grid's row
    count hides, decided here, never in the browser."""

    security_type: str
    names: int
    rows: int
    known: int
    share: float | None


@dataclass(frozen=True)
class KnownGapCount:
    """``names`` operating companies without a value for the one ``gap``."""

    gap: KnownGap
    names: int


@dataclass(frozen=True)
class KnownCoverage:
    """The share count of the session by security type, and the gaps of operating companies;
    ``unknown`` NOT_RUN when no nightly record of the session holds the breakdown (then no run
    id, no rows)."""

    session: date
    run_id: str | None
    by_type: tuple[KnownByType, ...]
    gaps: tuple[KnownGapCount, ...]
    unknown: Unknown | None


def _int(value: Any) -> int:
    return int(value) if isinstance(value, int | float) else 0


def _by_type(row: Mapping[str, Any]) -> KnownByType:
    names, known = _int(row.get("names")), _int(row.get("known"))
    return KnownByType(
        str(row.get("security_type", "")),
        names,
        _int(row.get("rows")),
        known,
        known / names if names else None,
    )


def load_known_coverage(ctx: ReadContext) -> KnownCoverage:
    """The breakdown of the newest nightly record of ``ctx.session.date`` that holds it."""
    day = ctx.session.date
    found = check_data(ctx, FUNDAMENTALS_FEATURE, BREAKDOWN)
    if found is None:
        why = run_cause(NIGHTLY, f"no coverage breakdown in a {NIGHTLY} record for {day}", day)
        return KnownCoverage(day, None, (), (), Unknown(UnknownCode.NOT_RUN, why))
    run_id, data = found
    stored = data[BREAKDOWN] if isinstance(data[BREAKDOWN], Mapping) else {}
    rows = stored.get("by_type")
    causes = stored.get("causes")
    by_type = tuple(
        _by_type(r) for r in (rows if isinstance(rows, list) else []) if isinstance(r, Mapping)
    )
    gaps = tuple(
        KnownGapCount(gap, _int(causes.get(gap.value)))
        for gap in KnownGap
        if isinstance(causes, Mapping) and causes.get(gap.value)
    )
    return KnownCoverage(day, run_id, by_type, gaps, None)
