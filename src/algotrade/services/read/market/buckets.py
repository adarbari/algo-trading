"""Pure downsampling of a market field's per-session history for a chart (ADR 0038: the
browser only draws what the server sends). No stores, no calendar: the caller passes the
exchange sessions of the window and one value per session (``None``: nothing stored).

- ``bucket_numbers``: at most ``points`` points. With no more sessions than ``points`` every
  session is a point; otherwise sessions fall into fixed buckets of ``bucket_sessions``
  consecutive sessions (the last may be shorter) and each bucket yields its minimum and its
  maximum at their own sessions (ties to the earliest), so a spike inside a bucket survives.
  A bucket with no stored value yields one null point at its first session (a null breaks the
  line); neighbouring empty buckets share one. A gap inside a bucket that has values is not
  visible: the bucket's extremes are the points.
- ``merge_segments``: a flag or a label as runs of consecutive sessions with one value
  (``ON`` / ``OFF`` / ``UNKNOWN`` for a flag, the text for a label, ``UNKNOWN`` where nothing
  is stored), the same merging the regime bands use."""

import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class Point:
    """One chart point; ``value`` is ``None`` for a gap."""

    session: date
    value: float | None


@dataclass(frozen=True)
class Segment:
    """Consecutive sessions ``start..end`` (the first and last of the run, inclusive) with
    the same ``value``."""

    start: date
    end: date
    value: str


def bucket_sessions_for(n_sessions: int, points: int) -> int:
    """Sessions per bucket so the result stays within ``points`` (1: every session). A bucket
    yields two points, so ``points // 2`` buckets cover the window."""
    if points < 2:
        raise ValueError(f"points must be at least 2, got {points}")
    if n_sessions <= points:
        return 1
    return math.ceil(n_sessions / (points // 2))


def bucket_numbers(
    sessions: Sequence[date], values: Sequence[float | None], points: int
) -> tuple[int, tuple[Point, ...]]:
    """``(bucket_sessions, points)`` for ``values`` (one per session, oldest first)."""
    if len(sessions) != len(values):
        raise ValueError("one value per session")
    size = bucket_sessions_for(len(sessions), points)
    out: list[Point] = []

    def gap(day: date) -> None:
        if not out or out[-1].value is not None:
            out.append(Point(day, None))

    for lo in range(0, len(sessions), size):
        known = [
            (i, v) for i in range(lo, min(lo + size, len(sessions))) if (v := values[i]) is not None
        ]
        if not known:
            gap(sessions[lo])
            continue
        # min / max return the first among equals: ties go to the earliest session
        low = min(known, key=lambda p: p[1])
        high = max(known, key=lambda p: p[1])
        for i, v in sorted({low, high}):
            out.append(Point(sessions[i], v))
    return size, tuple(out)


def merge_segments(sessions: Sequence[date], states: Sequence[str]) -> tuple[Segment, ...]:
    """Runs of consecutive ``sessions`` with the same state, oldest first."""
    if len(sessions) != len(states):
        raise ValueError("one state per session")
    out: list[Segment] = []
    for day, state in zip(sessions, states, strict=True):
        if out and out[-1].value == state:
            out[-1] = Segment(out[-1].start, day, state)
        else:
            out.append(Segment(day, day, state))
    return tuple(out)
