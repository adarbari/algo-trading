"""The weekly audit's comparison (ADR 0063 amendment 6, decision 9): the legs a full run computed
against the legs the incremental runs stored, by leg. A leg differs when it is not stored or any
column of its content differs; what a run stamps on a leg (the ``as_of`` of its outcome read and
the outcome partition's sequence) is not content, since the full run reads later than the leg
it checks. Pure: no store is read here."""

import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any

import numpy as np

from algotrade.services.evaluation.cross_section.legs.rows import (
    LEG,
    LegRecord,
    decode_leg,
    encode_leg,
)

type LegKey = tuple[str, str, str, int, date]  # leg key, edge variant, screener, horizon, D

STAMPS = frozenset({"outcomes_as_of", "outcome_seq"})  # what a run stamps, not what a leg holds
ABSENT = "not stored"


@dataclass(frozen=True)
class LegDifference:
    """One leg the full run holds differently: the columns that differ, or ``ABSENT``."""

    key: LegKey
    columns: tuple[str, ...]

    def describe(self) -> str:
        """``<screener> h<horizon> <day>: <columns>``, for a failure message."""
        _, _, variant, horizon, day = self.key
        return f"{variant} h{horizon} {day.isoformat()}: {', '.join(self.columns)}"


def _same(a: Any, b: Any) -> bool:
    """Equal values, a NaN and a null alike and arrays element by element."""
    if _null(a) or _null(b):
        return _null(a) and _null(b)
    if isinstance(a, (list, tuple, np.ndarray)) or isinstance(b, (list, tuple, np.ndarray)):
        left, right = np.asarray(a), np.asarray(b)
        if left.shape != right.shape:
            return False
        if left.dtype.kind in "fiu" and right.dtype.kind in "fiu":
            return bool(np.array_equal(left, right, equal_nan=True))
        # strings, or numbers with null elements (leg v2's pick lists): element by element
        return all(_same(x, y) for x, y in zip(left.tolist(), right.tolist(), strict=True))
    return bool(a == b)


def _null(value: Any) -> bool:
    return value is None or (isinstance(value, float) and math.isnan(value))


def _key(record: LegRecord) -> LegKey:
    return (record.key, record.edge_variant, record.variant, record.horizon, record.day)


def differing_legs(
    full: Iterable[Mapping[str, Any]],
    stored: Mapping[LegKey, LegRecord],
    user_id: str,
    edge_id: str,
) -> list[LegDifference]:
    """The legs among the ``leg`` rows of a full run (``EdgeEvaluation.leg_rows``) that differ from
    ``stored`` (``StoredLegs.legs``), in key order. A tombstone is skipped; a stored leg the full
    run does not hold is not reported: the run's range and trials bound what it checks."""
    found = []
    for row in full:
        if row["row_kind"] != LEG or row.get("tombstone"):
            continue  # a tombstone says a leg is gone: nothing was computed to compare
        fresh = decode_leg(row)
        old = stored.get(_key(fresh))
        if old is None:
            found.append(LegDifference(_key(fresh), (ABSENT,)))
            continue
        # both sides through the stored form (float32 draws), so a round trip is not a difference
        now, then = encode_leg(fresh, user_id, edge_id), encode_leg(old, user_id, edge_id)
        columns = tuple(c for c in now if c not in STAMPS and not _same(now[c], then.get(c)))
        if columns:
            found.append(LegDifference(_key(fresh), columns))
    return sorted(found, key=lambda d: (d.key[4], d.key[:4]))


def keep_differing(
    rows: Sequence[Mapping[str, Any]], differing: Sequence[LegDifference]
) -> tuple[Mapping[str, Any], ...]:
    """The rows of a full run to publish: every row (leg, reads, outcome) of each decision
    session holding a differing leg, so the session's reads row and its legs stay one
    consistent set (the invariant of ADR 0063's reuse rule)."""
    days = {d.key[4] for d in differing}
    return tuple(r for r in rows if _day(r["session_date"]) in days)


def _day(value: Any) -> date:
    return value.date() if hasattr(value, "date") else date(value.year, value.month, value.day)
