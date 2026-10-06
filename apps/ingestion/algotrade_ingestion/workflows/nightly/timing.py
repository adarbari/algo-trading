"""Run timing for the nightly report (pure): when each step ran, how long, how fast, vs before.

Steps run one after another, so a step's start is the run's start plus the durations of the
steps before it (per session, oldest first, then the final steps). Each ``StepTiming`` has its
share of the run, the items it processed and the throughput (items / min), sub-step timings
where the step result has them (each rollup's ``seconds``), and the trend: the previous
nightly's duration for that step, the median of the last ``HISTORY`` nightlies, and whether it
was more than ``SLOWER`` (50 %) slower than that median (or the previous run, with no median).
``vendor_pacing`` reads what each step's vendor limiters did (``stats.pacing`` of its run
record; keys in docs/configuration.md "Pacing stats"): requests, 429s, time waited.

Arrivals (ADR 0043): each attempt for the latest session records, per source-fed step, the
minutes after the close it started, whether the source had published the session and (chains)
the stale share: ``observe`` makes the first two from the step's checks, the nightly adds the
minutes and stores it as ``arrival`` in the step's result of the ``nightly`` run record.
``arrival_stats`` turns the last sessions' records into, per step, the p50 / p90 minutes after
close of the first attempt that found the data published.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
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
    "etf-holdings": "funds",
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
    "etf-holdings": "requested",
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


@dataclass(frozen=True)
class PacingLine:
    """One vendor limiter during one step's run (``stats.pacing.<key>``)."""

    session: str
    step: str
    key: str  # the limiter key (``cboe``, ``massive``...)
    requests: int
    throttled_429: int
    retry_after_wait_s: float
    limiter_wait_s: float
    error_rate_slowdowns: int
    interval_min_s: float | None
    interval_max_s: float | None
    interval_final_s: float | None


def _num(value: Any) -> float | None:
    return float(value) if isinstance(value, int | float) else None


def vendor_pacing(session: str, step: str, pacing: Any) -> list[PacingLine]:
    """``stats.pacing`` of a step's run record -> one line per limiter key (sorted)."""
    if not isinstance(pacing, Mapping):
        return []
    out = []
    for key, s in sorted(pacing.items()):
        if not isinstance(s, Mapping):
            continue
        out.append(
            PacingLine(
                session,
                step,
                str(key),
                int(s.get("requests") or 0),
                int(s.get("throttled_429") or 0),
                float(s.get("retry_after_wait_s") or 0.0),
                float(s.get("limiter_wait_s") or 0.0),
                int(s.get("error_rate_slowdowns") or 0),
                _num(s.get("interval_min_s")),
                _num(s.get("interval_max_s")),
                _num(s.get("interval_final_s")),
            )
        )
    return out


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


# The checks that say whether a source-fed step's data had been published (quality.py).
OBSERVED: Mapping[str, tuple[str, ...]] = {
    "bars": ("bars_fresh",),
    "chains": ("chains_stale_core", "chains_stale_rest"),
}
DEFAULT_SESSIONS = 20


def observe(step: str, checks: Sequence[Any]) -> dict[str, Any] | None:
    """What an attempt saw of the source: ``published`` (every publication check PASSed) and,
    for chains, the worst tier's ``stale_share``. ``None`` for a step that is not source-fed
    or whose checks did not run."""
    names = OBSERVED.get(step)
    seen = [c for c in checks if names and c.name in names]
    if not seen:
        return None
    out: dict[str, Any] = {"published": all(c.status == "PASS" for c in seen)}
    shares = [c.data["share"] for c in seen if "share" in c.data]
    if shares:
        out["stale_share"] = round(max(shares), 4)
    return out


def minutes_after_close(start: datetime, close: datetime) -> float:
    """Minutes from the session's ``close`` to an attempt's ``start`` (negative: before it)."""
    return round((start - close).total_seconds() / 60, 1)


@dataclass(frozen=True)
class ArrivalStat:
    step: str
    sessions: int  # sessions with an observed attempt
    bracketed: int  # an attempt saw "not published" before the first that saw it published
    p50: float | None  # minutes after close of the first published attempt, bracketed sessions
    p90: float | None
    immediate: int = 0  # the first attempt already found it published: arrival unknown, earlier
    earliest_immediate: float | None = None  # the earliest such first look (an upper bound)


def percentile(values: Sequence[float], q: float) -> float | None:
    """Linear-interpolated ``q`` (0..1) quantile; ``None`` for no values."""
    if not values:
        return None
    ordered = sorted(values)
    pos = (len(ordered) - 1) * q
    low = int(pos)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (pos - low)


def arrival_stats(
    attempts: Sequence[tuple[date, Mapping[str, Any]]], sessions: int = DEFAULT_SESSIONS
) -> tuple[ArrivalStat, ...]:
    """``attempts``: (session, a nightly attempt's steps) in any order. Per observed step, over
    the latest ``sessions`` sessions that have one. The arrival is known only between the last
    attempt that saw "not published" and the first that saw it published, so p50 / p90 use only
    those bracketed sessions (the first published attempt's minutes); a session whose first
    attempt already found it published is counted apart (``immediate``) with the earliest such
    first look, an upper bound that must not tune a wait."""
    out = []
    for step in OBSERVED:
        seen: dict[date, list[Mapping[str, Any]]] = {}
        for session, steps in attempts:
            arrival = (steps.get(step) or {}).get("arrival")
            if isinstance(arrival, Mapping) and isinstance(
                arrival.get("minutes_after_close"), int | float
            ):
                seen.setdefault(session, []).append(arrival)
        latest = sorted(seen)[-sessions:]
        bracketed: list[float] = []
        immediate: list[float] = []
        for day in latest:
            tries = sorted(seen[day], key=lambda a: a["minutes_after_close"])
            first = next((a for a in tries if a.get("published")), None)
            if first is None:
                continue
            if tries[0] is first:
                immediate.append(first["minutes_after_close"])
            else:
                bracketed.append(first["minutes_after_close"])
        if latest:
            out.append(
                ArrivalStat(
                    step,
                    len(latest),
                    len(bracketed),
                    percentile(bracketed, 0.5),
                    percentile(bracketed, 0.9),
                    len(immediate),
                    min(immediate) if immediate else None,
                )
            )
    return tuple(out)


def arrival_line(stat: ArrivalStat) -> str:
    """``first published: p50 X min, p90 Y min after close (b of n sessions)`` over the
    bracketed sessions, then the sessions already published at the first look."""
    if stat.p50 is None or stat.p90 is None:
        text = f"no bracketed arrival yet in {stat.sessions} observed sessions"
    else:
        text = (
            f"first published: p50 {stat.p50:.0f} min, p90 {stat.p90:.0f} min after close "
            f"({stat.bracketed} of {stat.sessions} sessions)"
        )
    if stat.immediate:
        text += (
            f"; {stat.immediate} already published at the first look (earliest "
            f"{stat.earliest_immediate:.0f} min after close, an upper bound)"
        )
    return text
