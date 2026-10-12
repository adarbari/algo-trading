"""``AcceptedFormula``: the formulas traders accepted in Describe it (``formula_accepted`` events of
``feedback/drafting_events``, whose payload carries the saved feature's expression and
fingerprint), grouped by fingerprint for the admin's backlog (ADR 0066 note 2026-10-11), over a
**date range** ending at the exchange date ``today`` (session-free, like the other feedback reads).

The privacy rules are here, server side: the role is the registry's (``Viewer.role``) and a trader
asking gets ``PermissionDeniedError`` before anything is read; a row is **counts only** (the
distinct users, never a user id). The formula text is strategy content, shown to admins only; a
row whose payload was nulled by retain / erase, or recorded before the payload held a fingerprint,
is skipped. ``duplicate_of`` is the site feature with the same fingerprint now; ``backlog_key`` an
exact match only (the feature's name, ``draft_`` stripped, a key or alias of the backlog, or the
backlog item promoted to ``duplicate_of``), never a fuzzy one."""

import json
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pandas as pd

from algotrade.config.site.drafting.backlog import BacklogItem
from algotrade.config.site.settings import load_feature_backlog
from algotrade.config.site.users import Role
from algotrade.core.model.errors import ConfigurationError, PermissionDeniedError
from algotrade.core.time.calendar import exchange_date
from algotrade.data.feedback import read_drafting_events
from algotrade.features.expressions.fingerprint import fingerprint
from algotrade.features.site import site_features
from algotrade.services.feedback.events import FORMULA_ACCEPTED
from algotrade.services.read.context import Stores
from algotrade.services.read.users.viewer import Viewer
from algotrade.services.read.values import to_scalar

WINDOW_DAYS = 365
COLUMNS = ("event_id", "ts", "user", "event", "payload", "session_date")
DRAFT_PREFIX = "draft_"  # the name Describe it proposes a formula under


@dataclass(frozen=True)
class AcceptedFormula:
    """One distinct formula (a fingerprint) traders accepted: ``accepted_count`` the distinct
    events, ``users`` the distinct accepters (a count, never who); ``expression`` and the rest of
    the newest row; ``duplicate_of`` the site feature it equals now (``""`` none), ``backlog_key``
    the backlog item it exactly matches (``""`` none)."""

    fingerprint: str
    canonical: str
    expression: str
    unit: str
    description: str
    accepted_count: int
    users: int
    first_accepted: date
    last_accepted: date
    duplicate_of: str
    backlog_key: str


@dataclass(frozen=True)
class AcceptedFormulaList:
    """The accepted formulas of the last ``days`` days up to ``today``, an admin's view."""

    today: date
    days: int
    rows: tuple[AcceptedFormula, ...]


def _payload(value: Any) -> Mapping[str, Any] | None:
    """The row's payload as an object, ``None`` for a null, unreadable or non-object one."""
    text = to_scalar(value)
    if not text:
        return None
    try:
        parsed = json.loads(str(text))
    except ValueError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _day(value: Any) -> date:
    return pd.Timestamp(value).date()


def _backlog_key(names: set[str], duplicate_of: str, items: tuple[BacklogItem, ...]) -> str:
    """The key of the backlog item an exact name (or the promoted site feature) points to."""
    by_name = {i.key: i.key for i in items} | {a: i.key for i in items for a in i.aliases}
    for name in sorted(names):
        bare = name.removeprefix(DRAFT_PREFIX)
        if bare in by_name:
            return by_name[bare]
    for item in items:
        if duplicate_of and item.promoted_to == duplicate_of:
            return item.key
    return ""


def _site_by_fingerprint(ctx: Stores) -> dict[str, str]:
    """The site's expression features by fingerprint (the first of equal ones), fingerprinted
    once; one that does not parse is skipped."""
    found: dict[str, str] = {}
    for expression in site_features(ctx.configs).expressions.values():
        if expression.scope != "site":
            continue
        try:
            found.setdefault(fingerprint(expression.definition).hash, expression.definition.name)
        except ConfigurationError:
            continue
    return found


def load_accepted_formulas(
    ctx: Stores, viewer: Viewer, since: date, today: date | None = None
) -> tuple[AcceptedFormula, ...]:
    """The formulas accepted from ``since`` to ``today`` (default: the exchange date now), grouped
    by fingerprint, most users first, then most accepted, then latest (admin only:
    ``PermissionDeniedError`` for anyone else, before anything is read)."""
    if viewer.role != Role.ADMIN.value:
        raise PermissionDeniedError("only an admin can read the accepted formulas")
    today = today or exchange_date(datetime.now(UTC))
    stored = read_drafting_events(ctx.reader, since, today)
    if stored is None or stored.empty:
        return ()
    frame = stored.reindex(columns=list(COLUMNS))
    frame = frame[frame["event"] == FORMULA_ACCEPTED].sort_values("ts", kind="stable")
    groups: dict[str, list[tuple[Mapping[str, Any], str, str, date]]] = defaultdict(list)
    for row in frame.to_dict("records"):  # oldest first: the last of a group is the newest
        payload = _payload(row["payload"])
        if payload is None or not payload.get("fingerprint"):
            continue  # nulled by retain / erase, or recorded before the payload had one
        groups[str(payload["fingerprint"])].append(
            (payload, str(row["event_id"]), str(row["user"]), _day(row["session_date"]))
        )
    site = _site_by_fingerprint(ctx)
    items = load_feature_backlog(ctx.configs).items
    out = []
    for key, rows in groups.items():
        newest = rows[-1][0]
        canonical = str(newest.get("canonical") or "")
        duplicate = site.get(key, "")
        names = {str(p["feature"]) for p, *_ in rows if p.get("feature")}
        days = [d for *_, d in rows]
        out.append(
            AcceptedFormula(
                fingerprint=key,
                canonical=canonical,
                expression=str(newest.get("expression") or ""),
                unit=str(newest.get("unit") or ""),
                description=str(newest.get("description") or ""),
                accepted_count=len({event_id for _, event_id, _, _ in rows}),
                users=len({user for _, _, user, _ in rows}),
                first_accepted=min(days),
                last_accepted=max(days),
                duplicate_of=duplicate,
                backlog_key=_backlog_key(names, duplicate, items),
            )
        )
    return tuple(
        sorted(
            out,
            key=lambda f: (
                -f.users,
                -f.accepted_count,
                -f.last_accepted.toordinal(),
                f.fingerprint,
            ),
        )
    )


def load_accepted_formula_list(
    ctx: Stores, viewer: Viewer, today: date | None = None, days: int = WINDOW_DAYS
) -> AcceptedFormulaList:
    """The accepted formulas of the last ``days`` days as the admin page's read object
    (``PermissionDeniedError`` for anyone else)."""
    today = today or exchange_date(datetime.now(UTC))
    rows = load_accepted_formulas(ctx, viewer, today - timedelta(days=days), today)
    return AcceptedFormulaList(today=today, days=days, rows=rows)
