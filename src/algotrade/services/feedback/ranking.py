"""Rank the missing features traders asked for (ADR 0066 amendment 2026-10-11): pure, over rows
already read, no I/O.

Score of one feature = the sum over its **distinct users** of ``exp(-age_days / 60)``, the age
taken from each user's latest request for it, times a feasibility weight (``ROLLUP_FROM_STORED``
1.0, ``NEEDS_SOURCE`` 0.5, ``UNCLEAR`` 0.25). One user asking again and again counts once, fresher
each time; one count per (user, feature, day), so the raw ``requests`` count, which breaks ties
(then the later ``last_seen``, then the name), cannot be inflated within a day. No embeddings: two
slugs are one feature only when the curated backlog says so (a key or an alias). A slug the backlog
does not know is ``unmapped``: an admin merges it into a key or alias by a PR.

A feature the backlog has since PROMOTED or set WONT_DO keeps its history and its score but is
listed after every OPEN and unmapped one, with its status: what is still to decide comes first."""

import math
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date

from algotrade.config.site.drafting.backlog import BacklogItem, FeatureBacklogSettings

HALF_LIFE_DAYS = 60.0  # the decay constant of exp(-age / 60)
WEIGHTS = {"ROLLUP_FROM_STORED": 1.0, "NEEDS_SOURCE": 0.5, "UNCLEAR": 0.25}
UNMAPPED = "UNMAPPED"  # the status of a slug the backlog does not know


@dataclass(frozen=True)
class RequestRow:
    """One stored request: who, for what (``ref``: a key or slug), on which exchange day."""

    user: str
    ref: str
    day: date
    feasibility: str = "UNCLEAR"


@dataclass(frozen=True)
class RankedRequest:
    """One feature in the ranking. ``ref`` the backlog key, else the slug; ``requests`` the
    distinct (user, day) asks; ``status`` the backlog's (OPEN / PROMOTED / WONT_DO) or UNMAPPED."""

    ref: str
    description: str
    score: float
    users: int
    requests: int
    last_seen: date
    feasibility: str
    status: str
    unmapped: bool
    promoted_to: str = ""


def weight(feasibility: str) -> float:
    """The weight of a feasibility word (``UNCLEAR``'s for any other)."""
    return WEIGHTS.get(feasibility, WEIGHTS["UNCLEAR"])


def decay(age_days: int) -> float:
    """``exp(-age / 60)`` for an age in days (a future date counts as today)."""
    return math.exp(-max(0, age_days) / HALF_LIFE_DAYS)


def _index(backlog: FeatureBacklogSettings) -> dict[str, BacklogItem]:
    return {i.key: i for i in backlog.items} | {a: i for i in backlog.items for a in i.aliases}


def rank(
    rows: Iterable[RequestRow], backlog: FeatureBacklogSettings, today: date
) -> tuple[RankedRequest, ...]:
    """The features of ``rows`` ranked, best first. A ``ref`` that is a key or an alias of the
    backlog today counts under the key, whatever it was recorded as."""
    known = _index(backlog)
    asks: dict[str, set[tuple[str, date]]] = {}
    latest_row: dict[str, RequestRow] = {}
    for row in rows:
        ref = known[row.ref].key if row.ref in known else row.ref
        asks.setdefault(ref, set()).add((row.user, row.day))
        if ref not in latest_row or _recency(row) > _recency(latest_row[ref]):
            latest_row[ref] = row
    out = [_ranked(ref, days, latest_row[ref], known.get(ref), today) for ref, days in asks.items()]
    return tuple(sorted(out, key=_order))


def _recency(row: RequestRow) -> tuple[date, str, str]:
    """Which of two requests is the latest: the day, then (so that read order never decides) the
    user and the feasibility."""
    return (row.day, row.user, row.feasibility)


def _order(r: RankedRequest) -> tuple[int, float, int, int, str]:
    """Open and unmapped features first, then by score, raw count, recency and name."""
    closed = r.status not in ("OPEN", UNMAPPED)
    return (int(closed), -r.score, -r.requests, -r.last_seen.toordinal(), r.ref)


def _ranked(
    ref: str,
    asks: set[tuple[str, date]],
    latest: RequestRow,
    item: BacklogItem | None,
    today: date,
) -> RankedRequest:
    last_by_user: dict[str, date] = {}
    for user, day in asks:
        last_by_user[user] = max(day, last_by_user.get(user, day))
    feasibility = item.feasibility if item else latest.feasibility
    if feasibility not in WEIGHTS:
        feasibility = "UNCLEAR"
    score = sum(decay((today - d).days) for d in last_by_user.values()) * weight(feasibility)
    return RankedRequest(
        ref=ref,
        description=item.description if item else "",
        score=score,
        users=len(last_by_user),
        requests=len(asks),
        last_seen=max(last_by_user.values()),
        feasibility=feasibility,
        status=item.status if item else UNMAPPED,
        unmapped=item is None,
        promoted_to=item.promoted_to if item else "",
    )
