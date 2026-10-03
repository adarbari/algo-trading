"""Run timing for the nightly report (pure): when each step ran, how long, how fast, vs before.

Steps run one after another, so a step's start is the run's start plus the durations of the
steps before it (per session, oldest first, then the final steps). Each ``StepTiming`` has its
share of the run, the items it processed and the throughput (items / min), sub-step timings
where the step result has them (each rollup's ``seconds``), and the trend: the previous
nightly's duration for that step, the median of the last ``HISTORY`` nightlies, and whether it
was more than ``SLOWER`` (50 %) slower than that median (or the previous run, with no median).
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from statistics import median
from typing import Any

HISTORY = 7
SLOWER = 0.5
MIN_TREND_S = 5.0  # shorter steps are noise, never flagged
# What a step's "items" are, and where the count comes from (else the run record's items).
UNITS: Mapping[str, str] = {
    "universe-build": "instruments",
    "company-details": "CIKs",
    "shares": "CIKs",
    "earnings": "dates",
    "bars": "sessions",
    "rates": "years",
    "corporate-actions": "windows",
    "chains": "underlyings",
    "rollups": "rows",
    "screens": "screens",
    "quality": "checks",
}
RESULT_ITEMS: Mapping[str, str] = {
    "company-details": "requested",
    "shares": "requested",
    "universe-build": "covered",
}


@dataclass(frozen=True)
class StepTiming:
    session: str  # "" for the steps after every session
    step: str
    status: str
    start: datetime | None
    end: datetime | None
    duration_s: float
    share: float  # of the run's total duration, 0..1
    items: int | None
    unit: str
    per_min: float | None
    previous_s: float | None  # the step in the previous nightly
    median_s: float | None  # median over the last HISTORY nightlies
    slower: bool  # > SLOWER above the median (or previous)
    substeps: tuple[tuple[str, float], ...] = ()


def _items(step: str, result: Any, record_items: int | None) -> int | None:
    if not isinstance(result, Mapping):
        return record_items
    if step == "rollups":
        rows = [v.get("rows", 0) for k, v in result.items() if "@" in k and isinstance(v, Mapping)]
        return int(sum(rows)) if rows else record_items
    if step == "screens":
        return len(result.get("screens", []))
    key = RESULT_ITEMS.get(step)
    if key and isinstance(result.get(key), int):
        return int(result[key])
    return record_items


def _substeps(result: Any) -> tuple[tuple[str, float], ...]:
    if not isinstance(result, Mapping):
        return ()
    found = [
        (str(k), float(v["seconds"]))
        for k, v in result.items()
        if isinstance(v, Mapping) and isinstance(v.get("seconds"), int | float)
    ]
    return tuple(sorted(found, key=lambda kv: -kv[1]))


def _trend(step: str, history: Sequence[Mapping[str, float]]) -> tuple[float | None, float | None]:
    seen = [h[step] for h in history[:HISTORY] if step in h]
    previous = history[0].get(step) if history else None
    return previous, (median(seen) if seen else None)


def step_timings(
    steps: Sequence[tuple[str, str, Mapping[str, Any]]],
    started: datetime | None,
    total_s: float,
    record_items: Mapping[tuple[str, str], int],
    history: Sequence[Mapping[str, float]] = (),
) -> tuple[StepTiming, ...]:
    """``steps``: (session, name, step dict) in run order; ``record_items``: (session, step) ->
    items in its run record; ``history``: step -> seconds per earlier nightly, newest first."""
    out = []
    clock = started
    for session, name, step in steps:
        took = float(step.get("duration_s", 0.0))
        end = clock + timedelta(seconds=took) if clock else None
        result = step.get("result")
        items = _items(name, result, record_items.get((session, name)))
        previous, typical = _trend(name, history)
        base = typical if typical is not None else previous
        slower = base is not None and took >= MIN_TREND_S and took > base * (1 + SLOWER)
        out.append(
            StepTiming(
                session,
                name,
                str(step.get("status")),
                clock,
                end,
                took,
                took / total_s if total_s > 0 else 0.0,
                items,
                UNITS.get(name, "items"),
                items / (took / 60) if items and took >= 1 else None,
                previous,
                typical,
                slower,
                _substeps(result),
            )
        )
        clock = end
    return tuple(out)
