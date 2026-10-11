"""Summarise a run record's per-item statuses: the status code, which codes are fine, and the
items that failed grouped by a normalised reason (shared by the nightly report and the API); and
the option-chain coverage of a session over its recent run records (``chain_coverage``).

An item status is ``CODE`` or ``CODE: message`` (``STALE_DATA: chain is for 2026-10-01``).
The reason is the status without what makes every item's message different (its own key,
URLs, dates, numbers), so one cause is one group however many items it hit.
"""

import re
import statistics
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date

from algotrade.storage.runs import RunRecord

# Item statuses that are not failures: stored, or "nothing to fetch" outcomes counted in stats.
FINE = frozenset(
    {"OK", "STORED", "PASS", "COMPLETE", "SKIPPED", "NO_SESSION", "EMPTY", "NO_FACTS"}
    | {"NO_SHARE_FACTS", "NO_INPUT"}
)
_URL = re.compile(r"https?://\S+")
_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
_NUMBER = re.compile(r"\b\d+(\.\d+)?\b")


def status_code(status: str) -> str:
    """``CODE: message`` -> ``CODE``."""
    return status.split(":", 1)[0].strip()


def normalise(message: str, key: str = "") -> str:
    """A failure reason without the specifics that make every item's message different."""
    # The key as a whole token only: ticker "E" must not turn STALE_DATA into STAL<id>_DATA.
    text = re.sub(rf"(?<!\w){re.escape(key)}(?!\w)", "<id>", message) if key else message
    text = _URL.sub("<url>", text)
    text = _DATE.sub("<date>", text)
    return _NUMBER.sub("<n>", text).strip()


def failed_items(items: Mapping[str, str]) -> list[tuple[str, list[tuple[str, str]]]]:
    """(reason, [(item key, status)]) for every item whose code is not ``FINE``: the largest
    group first, keys sorted within a group."""
    grouped: dict[str, list[tuple[str, str]]] = {}
    for key, status in sorted(items.items()):
        if status_code(status) not in FINE:
            grouped.setdefault(normalise(status, key), []).append((key, status))
    return sorted(grouped.items(), key=lambda kv: (-len(kv[1]), kv[0]))


# Chain coverage (the option-chains task's per-underlying statuses): the share of the optionable
# universe whose chain was fetched OK, the names the feed keeps serving stale, and when either
# drifts. Cboe's free delayed feed chronically leaves hundreds of underlyings STALE_DATA, which the
# acceptance check's share limit tolerates, so the gap is shown every session instead.
CHAINS_JOB = "option_chains"
STALE_STATUS = "STALE_DATA"
CHRONIC_WINDOW = 5  # sessions looked at, the session read and the four before
CHRONIC_MIN = 3  # stale in at least this many of them is chronic
TOP_CHRONIC = 10
DRIFT_POINTS = 0.05  # coverage this far (share) below its median of the sessions before warns
DRIFT_CHRONIC = 50  # this many more chronic names than the session before warns


@dataclass(frozen=True)
class ChainCoverage:
    """One session's chain coverage: ``ok`` of ``total`` underlyings fetched OK (``share``),
    ``statuses`` the status code counts, ``tiers`` the fetch-order tier sizes the run recorded,
    ``chronic`` the names stale in ``CHRONIC_MIN`` of the last ``CHRONIC_WINDOW`` sessions
    (``chronic_top`` the most persistent, instrument ids), and the two drift references:
    ``median_share`` of the sessions before and ``previous_chronic`` the session before's count."""

    session: str
    total: int
    ok: int
    share: float
    statuses: tuple[tuple[str, int], ...]
    tiers: tuple[tuple[str, int], ...]
    chronic: int
    chronic_top: tuple[str, ...]
    median_share: float | None = None
    previous_chronic: int | None = None

    def drift(self) -> tuple[str, ...]:
        """What moved beyond the drift limits (empty when nothing did or nothing to compare)."""
        out = []
        if self.median_share is not None and self.share < self.median_share - DRIFT_POINTS:
            out.append(
                f"chain coverage {self.share:.1%} is {(self.median_share - self.share) * 100:.1f} "
                f"points below its median of the sessions before ({self.median_share:.1%})"
            )
        if (
            self.previous_chronic is not None
            and self.chronic - self.previous_chronic > DRIFT_CHRONIC
        ):
            out.append(
                f"chronic stale chains rose to {self.chronic} from {self.previous_chronic} "
                f"the session before"
            )
        return tuple(out)


def _latest_items(records: Iterable[RunRecord]) -> dict[date, RunRecord]:
    """The latest record with items of each session."""
    found: dict[date, RunRecord] = {}
    for r in sorted(records, key=lambda r: r.started_at):
        if r.items:
            found[r.session_date] = r
    return found


def _chronic(by_day: Mapping[date, RunRecord], days: Sequence[date]) -> Counter[str]:
    """Stale-session count of each name stale in ``CHRONIC_MIN`` or more of ``days``."""
    stale: Counter[str] = Counter()
    for day in days:
        record = by_day.get(day)
        stale.update(
            k for k, s in (record.items if record else {}).items() if status_code(s) == STALE_STATUS
        )
    return Counter({k: n for k, n in stale.items() if n >= CHRONIC_MIN})


def chain_coverage(records: Iterable[RunRecord], days: Sequence[date]) -> ChainCoverage | None:
    """The coverage of ``days[-1]`` from the chains task's run ``records`` of ``days`` (the
    sessions oldest first, ``CHRONIC_WINDOW + 1`` of them to compare with the five before);
    ``None`` when the session has no chains record."""
    by_day = _latest_items(records)
    record = by_day.get(days[-1]) if days else None
    if record is None:
        return None
    codes = Counter(status_code(s) for s in record.items.values())
    chronic = _chronic(by_day, days[-CHRONIC_WINDOW:])
    before = days[:-1][-CHRONIC_WINDOW:]
    shares = [
        sum(1 for s in by_day[d].items.values() if status_code(s) == "OK") / len(by_day[d].items)
        for d in before
        if d in by_day
    ]
    previous = (
        len(_chronic(by_day, before))
        if len(before) == CHRONIC_WINDOW and before[-1] in by_day
        else None
    )
    tiers = record.stats.get("order_tiers")
    ok = codes.get("OK", 0)
    total = len(record.items)
    return ChainCoverage(
        session=days[-1].isoformat(),
        total=total,
        ok=ok,
        share=ok / total,
        statuses=tuple(codes.most_common()),
        tiers=tuple((str(k), int(v)) for k, v in tiers.items())
        if isinstance(tiers, Mapping)
        else (),
        chronic=len(chronic),
        chronic_top=tuple(
            k for k, _ in sorted(chronic.items(), key=lambda kv: (-kv[1], kv[0]))[:TOP_CHRONIC]
        ),
        median_share=statistics.median(shares) if len(shares) >= 3 else None,
        previous_chronic=previous,
    )
