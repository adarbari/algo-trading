"""The missing-feature requests (``feedback/feature_requests``, ADR 0066 amendment 2026-10-11) a
viewer may read, over a **date range** ending at the exchange date ``today`` (session-free, like
the usage and the drafting-events reads).

The privacy rules are here, server side, the role being the registry's (``Viewer.role``), never
the client's: ``load_my_requests`` returns the viewer's **own** history only (per feature: first
and last asked, times asked), for a trader and an admin alike, and never a count or a trace of
another user; ``load_ranked_requests`` is the admin's ordered list across users (score, distinct
users, last seen, feasibility, status from the backlog, unmapped slugs flagged), and a trader
asking for it gets ``PermissionDeniedError``. The ranking itself is ``services/feedback/ranking``.
A column an older partition lacks reads as null. ``load_feature_requests`` is the admin page's
read object (``FeatureRequestList``): the ranking as rows, **counts only** (never a user id or a
span), over the date range ending today."""

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

import pandas as pd

from algotrade.config.site.drafting.backlog import BacklogItem
from algotrade.config.site.settings import load_feature_backlog
from algotrade.config.site.users import Role
from algotrade.core.model.errors import PermissionDeniedError
from algotrade.core.time.calendar import exchange_date
from algotrade.data.feedback import read_feature_requests
from algotrade.services.feedback.ranking import UNMAPPED, RankedRequest, RequestRow, rank
from algotrade.services.read.context import Stores
from algotrade.services.read.users.viewer import Viewer
from algotrade.services.read.values import to_scalar

WINDOW_DAYS = 365  # the history read: a request older than this has decayed to under 3%
COLUMNS = ("user", "ref", "feasibility", "session_date", "ts", "span")


@dataclass(frozen=True)
class MyRequest:
    """One feature the viewer asked for: ``ref`` the backlog key (an alias counts under its key)
    or the slug of a request not yet mapped; ``times_asked`` the distinct days."""

    ref: str
    description: str
    status: str
    unmapped: bool
    first_asked: date
    last_asked: date
    times_asked: int
    promoted_to: str = ""
    feasibility: str = "UNCLEAR"  # of the latest ask (the backlog item's when it has one)
    span: str | None = None  # the piece of the viewer's own sentence of the latest ask
    asked_before_today: bool = False  # an ask on an earlier exchange date than ``today``


@dataclass(frozen=True)
class FeatureRequestRow:
    """One feature in the admin list, counts only: ``rank`` 1-based in the ranking's order;
    ``ref`` the backlog key (else the unmapped slug); ``users`` the distinct askers, ``times_asked``
    the distinct (user, day) asks; ``status`` OPEN / PROMOTED / WONT_DO or UNMAPPED."""

    rank: int
    ref: str
    description: str
    feasibility: str
    score: float
    users: int
    times_asked: int
    first_seen: date | None
    last_seen: date
    status: str
    promoted_to: str
    unmapped: bool


@dataclass(frozen=True)
class FeatureRequestList:
    """The ranked requests of the last ``days`` days up to ``today``, an admin's view."""

    today: date
    days: int
    rows: tuple[FeatureRequestRow, ...]


def _stored(ctx: Stores, since: date, today: date) -> pd.DataFrame:
    stored = read_feature_requests(ctx.reader, since, today)
    if stored is None or stored.empty:
        return pd.DataFrame(columns=list(COLUMNS))
    return stored.reindex(columns=list(COLUMNS))  # older partitions may lack a column


def _rows(frame: pd.DataFrame) -> list[RequestRow]:
    return [
        RequestRow(
            str(r["user"]),
            str(r["ref"]),
            pd.Timestamp(r["session_date"]).date(),
            str(to_scalar(r["feasibility"]) or "UNCLEAR"),
        )
        for r in frame.to_dict("records")
    ]


def load_my_requests(
    ctx: Stores, viewer: Viewer, today: date | None = None, days: int = WINDOW_DAYS
) -> tuple[MyRequest, ...]:
    """The viewer's own requests of the last ``days`` days, one per feature, most recently asked
    first. The filter is on ``viewer.user_id`` for every role: nobody's history but their own."""
    today = today or exchange_date(datetime.now(UTC))
    frame = _stored(ctx, today - timedelta(days=days), today)
    own = frame[frame["user"] == viewer.user_id].sort_values("ts", kind="stable")
    mine = _rows(own)
    latest = {  # the newest ask per row's ref: its feasibility and span
        str(r["ref"]): (
            str(to_scalar(r["feasibility"]) or "UNCLEAR"),
            str(span) if (span := to_scalar(r["span"])) else None,
        )
        for r in own.to_dict("records")
    }
    backlog = load_feature_backlog(ctx.configs)
    by_name: dict[str, BacklogItem] = {i.key: i for i in backlog.items}
    by_name |= {a: i for i in backlog.items for a in i.aliases}
    days_by_ref: dict[str, set[date]] = {}
    last_of: dict[str, tuple[str, str | None]] = {}
    for row in mine:
        ref = by_name[row.ref].key if row.ref in by_name else row.ref
        days_by_ref.setdefault(ref, set()).add(row.day)
        last_of[ref] = latest[row.ref]  # mine is in time order: the newest ask wins
    out = []
    for ref, asked in days_by_ref.items():
        item = by_name.get(ref)
        feasibility, span = last_of[ref]
        out.append(
            MyRequest(
                ref=ref,
                description=item.description if item else "",
                status=item.status if item else UNMAPPED,
                unmapped=item is None,
                first_asked=min(asked),
                last_asked=max(asked),
                times_asked=len(asked),
                promoted_to=item.promoted_to if item else "",
                feasibility=item.feasibility if item else feasibility,
                span=span,
                asked_before_today=min(asked) < today,
            )
        )
    return tuple(sorted(out, key=lambda r: (-r.last_asked.toordinal(), r.ref)))


def load_ranked_requests(
    ctx: Stores, viewer: Viewer, today: date | None = None, days: int = WINDOW_DAYS
) -> tuple[RankedRequest, ...]:
    """The requests of the last ``days`` days of every user, ranked (admin only):
    ``PermissionDeniedError`` for anyone else, before anything is read."""
    if viewer.role != Role.ADMIN.value:
        raise PermissionDeniedError("only an admin can read the ranked feature requests")
    today = today or exchange_date(datetime.now(UTC))
    frame = _stored(ctx, today - timedelta(days=days), today)
    return rank(_rows(frame), load_feature_backlog(ctx.configs), today)


def load_feature_requests(
    ctx: Stores, viewer: Viewer, today: date | None = None, days: int = WINDOW_DAYS
) -> FeatureRequestList:
    """The ranked list as rows for the admin page (``PermissionDeniedError`` for anyone else)."""
    today = today or exchange_date(datetime.now(UTC))
    ranked = load_ranked_requests(ctx, viewer, today, days)
    rows = tuple(
        FeatureRequestRow(
            rank=i,
            ref=r.ref,
            description=r.description,
            feasibility=r.feasibility,
            score=r.score,
            users=r.users,
            times_asked=r.requests,
            first_seen=r.first_seen,
            last_seen=r.last_seen,
            status=r.status,
            promoted_to=r.promoted_to,
            unmapped=r.unmapped,
        )
        for i, r in enumerate(ranked, start=1)
    )
    return FeatureRequestList(today=today, days=days, rows=rows)
