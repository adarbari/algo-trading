"""Ideas (ADR 0029): one row per ticker listing every screener that picked it, ranked by the
user's screener priority, then score, the tie-break and instrument id.

Read-only over stored ``results/rule_screen`` (and ``results/rule_screen_values`` for the
reasons): for each config the rows of its latest run (``run_id``) in its latest session on or
before the date. A screen is never recomputed here. A ticker is *picked* by a screener when
its decision is not REJECT, SKIPPED or UNKNOWN.

Display context comes from the stored rollups on the newest session they cover: the next
earnings date and sessions to it (``earnings@v1``). The closest listed expiry is read on the fly
for the shown tickers from the session's stored chains (one pruned read, nothing later is
visible): the nearest expiry on or after the session, and its DTE in calendar days from the
session (``option_liquidity@v1``'s ``target_dte`` convention, but for the nearest expiry, not the
target one). ``earnings_before_expiry`` is true when the next earnings date is on or before it.

Each pick carries its screener's stored display columns (the ``INFO`` rows of
``rule_screen_values``), the values of its criteria and its flags; ``Ideas.screeners`` lists
the screeners with their display name (the config's ``name``, else its id) and version. The
two stored tables are read column-pruned.
"""

from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import date
from typing import Any

import pandas as pd

from algotrade.config.user import SITE_USER, UserContext
from algotrade.data import StoreReader
from algotrade.data.chains import chain_expiries
from algotrade.data.reference import resolver, snapshot
from algotrade.data.rollups import rollup_on
from algotrade.features.rollups import earnings
from algotrade.services.explore.store import NotFoundError, ReadStore
from algotrade.services.views import to_value
from algotrade.storage.tables.schemas import result_table

RULE_SCREEN = result_table("rule_screen")
RULE_SCREEN_VALUES = result_table("rule_screen_values")
PREFERENCES = "preferences"
SCREEN_COLUMNS = (
    "user_id", "config_id", "config_version", "decision", "score", "tie_break", "tier", "class",
    "flags", "reasons",
)  # fmt: skip
VALUE_COLUMNS = (
    "user_id",
    "config_id",
    "criterion_id",
    "mode",
    "field",
    "outcome",
    "value_num",
    "value_str",
    "distance",
)  # fmt: skip  (the table's key columns stay: runs merge by key)
LOOKBACK = 20  # newest rule_screen sessions scanned for each config's latest run
NOT_PICKED = frozenset({"REJECT", "SKIPPED", "UNKNOWN"})


@dataclass(frozen=True)
class PickCriterion:
    criterion_id: str
    field: str
    outcome: str  # NEAR / FAIL / MISSING
    value: float | str | None
    distance: float | None


@dataclass(frozen=True)
class Pick:
    config_id: str
    user: str
    config_version: int | None
    session: date
    decision: str
    score: float | None
    tier: str | None
    klass: str | None
    reasons: str
    criteria: list[PickCriterion]  # the criteria that did not pass
    columns: dict[str, Any]  # the screen's display columns
    criterion_values: dict[str, Any]  # criterion id -> the value it was judged on
    flags: list[str]  # the screen's flags that hold (e.g. leveraged_inverse)


@dataclass(frozen=True)
class Idea:
    rank: int
    instrument_id: str
    symbol: str | None
    picks: list[Pick]  # highest-priority screener first
    next_earnings_date: date | None
    days_to_earnings: int | None
    closest_expiry_dte: int | None  # None: no stored chain for the session
    earnings_before_expiry: bool | None  # None: no earnings date or no chain


@dataclass(frozen=True)
class IdeaScreener:
    config_id: str
    user: str | None  # None: no stored run in the window
    name: str  # display name: the config's ``name``, else its id
    version: int | None


@dataclass(frozen=True)
class Ideas:
    session: date  # the newest session any screen contributed
    priority: list[str]
    screeners: list[IdeaScreener]  # priority order, then any other screener with picks
    total: int
    items: list[Idea]


def screener_priority(store: ReadStore, user: str) -> list[str]:
    """``ideas.priority`` of ``config/users/<user>/preferences.toml`` (screener ids, best first)."""
    doc = store.configs.load(user, PREFERENCES, PREFERENCES) or {}
    found = (doc.get("ideas") or {}).get("priority") or []
    return [str(i) for i in found]


def ideas_for(store: ReadStore, on: date | None, user: str | None, limit: int) -> Ideas:
    """``top_ideas`` for ``user`` (default: the store's) and their stored screener priority."""
    who = UserContext(user).user_id if user else store.user.user_id
    found = top_ideas(store.reader, on, who, screener_priority(store, who), limit)
    names = {s.config_id: _display_name(store, who, s.config_id) for s in found.screeners}
    return replace(
        found, screeners=[replace(s, name=names[s.config_id] or s.name) for s in found.screeners]
    )


def _display_name(store: ReadStore, user: str, config_id: str) -> str | None:
    """The ``name`` of the user's screener ``config_id``, else of the site preset it extends."""
    for scope in dict.fromkeys([user, SITE_USER]):
        doc = store.configs.load(scope, "screeners", config_id) or {}
        if isinstance(doc.get("name"), str) and doc["name"].strip():
            return str(doc["name"]).strip()
    return None


def _screeners(frames: list[pd.DataFrame], priority: Sequence[str]) -> list[IdeaScreener]:
    """The screeners with a stored run, listed ids first (best first), then the rest by id."""
    seen: dict[str, IdeaScreener] = {}
    for frame in frames:
        first = frame.iloc[0]
        version = to_value(first.get("config_version"))
        cid = str(first["config_id"])
        seen[cid] = IdeaScreener(
            cid, str(first["user_id"]), cid, None if version is None else int(version)
        )
    listed = list(dict.fromkeys(priority))
    return [seen.get(c) or IdeaScreener(c, None, c, None) for c in listed] + [
        seen[c] for c in sorted(seen) if c not in listed
    ]


def _latest_runs(reader: StoreReader, on: date | None, user: str) -> list[pd.DataFrame]:
    """Per config, its rows of the latest run in its latest session (the user's own screen
    wins over a site screen of the same id). Each frame carries its ``_session``."""
    sessions = [d for d in reader.dates(RULE_SCREEN) if on is None or d <= on]
    if not sessions:
        raise NotFoundError(
            f"{RULE_SCREEN}: nothing stored" + (f" on or before {on}" if on else "")
        )
    latest: dict[tuple[str, str], pd.DataFrame] = {}
    for session in reversed(sessions[-LOOKBACK:]):
        frame = reader.table_range(RULE_SCREEN, session, session, None, None, SCREEN_COLUMNS)
        if frame is None or frame.empty:
            continue
        frame = frame[frame["user_id"].isin([user, SITE_USER])]
        for (owner, config_id), rows in frame.groupby(["user_id", "config_id"], sort=True):
            key = (str(owner), str(config_id))
            if key not in latest:
                run = rows.sort_values("knowledge_ts", kind="stable")["run_id"].iloc[-1]
                latest[key] = rows[rows["run_id"] == run].assign(_session=session)
    chosen: dict[str, pd.DataFrame] = {}
    for owner in (SITE_USER, user):  # the user's overwrite the site's
        chosen.update({c: f for (o, c), f in latest.items() if o == owner})
    return list(chosen.values())


def _float(value: object) -> float | None:
    out = to_value(value)
    return None if out is None else float(out)


def _text(value: object) -> str | None:
    out = to_value(value)
    return None if out is None or out == "" else str(out)


def _pick(row: dict[str, Any]) -> Pick:
    version = to_value(row.get("config_version"))
    score = _float(row.get("score"))
    return Pick(
        config_id=str(row["config_id"]),
        user=str(row["user_id"]),
        config_version=None if version is None else int(version),
        session=row["_session"],
        decision=str(row["decision"]),
        score=score,
        tier=_text(row.get("tier")),
        klass=_text(row.get("class")),
        reasons=str(to_value(row.get("reasons")) or ""),
        criteria=[],
        columns={},
        criterion_values={},
        flags=[f for f in str(to_value(row.get("flags")) or "").split(",") if f],
    )


def _candidates(
    frames: list[pd.DataFrame], rank_of: dict[str, int]
) -> dict[str, list[tuple[Any, Pick]]]:
    """``{instrument_id: [(sort key, pick)]}`` of the picks, best screener first."""
    out: dict[str, list[tuple[Any, Pick]]] = {}
    for frame in frames:
        for row in frame.to_dict("records"):
            if str(row["decision"]) in NOT_PICKED:
                continue
            pick = _pick({str(k): v for k, v in row.items()})
            tie = _float(row.get("tie_break"))
            key = (
                rank_of[pick.config_id],
                -(pick.score if pick.score is not None else -1.0),
                -(tie if tie is not None else float("-inf")),
                pick.config_id,
            )
            out.setdefault(str(row["instrument_id"]), []).append((key, pick))
    for picks in out.values():
        picks.sort(key=lambda kp: kp[0])
    return out


def _details(
    reader: StoreReader, picks: dict[str, list[Pick]]
) -> dict[tuple[str, str], pd.DataFrame]:
    """The stored per-criterion values of the shown tickers, per (config, session)."""
    wanted = sorted(picks)
    out: dict[tuple[str, str], pd.DataFrame] = {}
    for session in {p.session for ps in picks.values() for p in ps}:
        frame = reader.table_range(
            RULE_SCREEN_VALUES, session, session, None, wanted, VALUE_COLUMNS
        )
        if frame is None:
            continue
        frame = frame[frame["instrument_id"].isin(wanted)]  # the read prunes row groups only
        if frame.empty:
            continue
        for (owner, config_id), rows in frame.groupby(["user_id", "config_id"]):
            out[(f"{owner}/{config_id}", str(session))] = rows
    return out


def _attach_values(reader: StoreReader, picks: dict[str, list[Pick]]) -> dict[str, list[Pick]]:
    values = _details(reader, picks)
    done: dict[str, list[Pick]] = {}
    for iid, ps in picks.items():
        filled = []
        for p in ps:
            rows = values.get((f"{p.user}/{p.config_id}", str(p.session)))
            criteria: list[PickCriterion] = []
            columns: dict[str, Any] = {}
            judged: dict[str, Any] = {}
            if rows is not None:
                for r in rows[rows["instrument_id"] == iid].to_dict("records"):
                    num, text = to_value(r.get("value_num")), to_value(r.get("value_str"))
                    value = num if num is not None else text
                    if r["outcome"] == "INFO":
                        columns[str(r["criterion_id"])] = value
                        continue
                    if value is not None:
                        judged[str(r["criterion_id"])] = value
                    if r["outcome"] in ("NEAR", "FAIL", "MISSING"):
                        criteria.append(
                            PickCriterion(
                                str(r["criterion_id"]),
                                str(r["field"]),
                                str(r["outcome"]),
                                value,
                                _float(r.get("distance")),
                            )
                        )
            filled.append(replace(p, criteria=criteria, columns=columns, criterion_values=judged))
        done[iid] = filled
    return done


def _earnings(reader: StoreReader, on: date) -> dict[str, tuple[date | None, int | None]]:
    """``{instrument_id: (next earnings date, sessions to it)}`` from the stored rollup."""
    snap = snapshot(reader, earnings.GROUP.table, on)
    if snap is None or snap.pre_snapshot:
        return {}
    frame = rollup_on(reader, earnings.GROUP.table, snap.snapshot_date)
    if frame is None:
        return {}
    out: dict[str, tuple[date | None, int | None]] = {}
    for r in frame.to_dict("records"):
        when, days = to_value(r.get("next_earnings_date")), to_value(r.get("days_to_earnings"))
        out[str(r["instrument_id"])] = (
            None if when is None else date.fromisoformat(str(when)[:10]),
            None if days is None else int(days),
        )
    return out


def top_ideas(
    reader: StoreReader,
    on: date | None,
    user: str,
    priority: Sequence[str],
    limit: int,
) -> Ideas:
    """The ``limit`` best tickers picked by any of ``user``'s (or the site's) stored screens
    in sessions on or before ``on`` (the latest when None); ``priority`` lists screener ids,
    best first (screens not listed rank after, by id). ``NotFoundError`` when no screen results
    are stored by then."""
    frames = _latest_runs(reader, on, user)
    ids = sorted({str(c) for f in frames for c in f["config_id"].unique()})
    listed = {c: i for i, c in enumerate(priority)}
    rank_of = {c: listed.get(c, len(listed)) for c in ids}
    candidates = _candidates(frames, rank_of)
    ranked = sorted(candidates, key=lambda i: (candidates[i][0][0], i))
    shown = ranked[: max(limit, 0)]
    picks = _attach_values(reader, {i: [p for _, p in candidates[i]] for i in shown})
    session = max(f["_session"].iloc[0] for f in frames) if frames else None
    if session is None:
        raise NotFoundError(f"{RULE_SCREEN}: no results stored")
    names = resolver(reader, session)
    context = _earnings(reader, session)
    expiries = chain_expiries(reader, session, shown)
    items = []
    for n, iid in enumerate(shown, start=1):
        when, days = context.get(iid, (None, None))
        nearest = next((e for e in expiries.get(iid, []) if e >= session), None)
        dte = None if nearest is None else (nearest - session).days
        before = None if nearest is None or when is None else when <= nearest
        items.append(Idea(n, iid, names.symbol_for(iid), picks[iid], when, days, dte, before))
    return Ideas(session, list(priority), _screeners(frames, priority), len(ranked), items)
