"""A rule screen's latest run as a review table (ADR 0031): one row per instrument with its
decision, score and reasons, the value and PASS / NEAR / FAIL / MISSING of every criterion, the
screen's display columns, any catalogue features the reader adds, and what changed since the
previous run (``new`` / ``dropped``).

Read-only over stored ``results/rule_screen`` and ``results/rule_screen_values``: nothing is
recomputed. A run holds a row for every instrument of the day's snapshot (about 11k), so the
rows are filtered (decision, change, search), sorted and paged here; the finished table is
cached per query and published state, and the reader pages through it. A ticker is *picked*
when its decision is not in ``NOT_PICKED`` (the Ideas rule); a change compares that with the
previous stored session of the same screen.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

import pandas as pd

from algotrade.config.strategy.schema import RULES_IMPL
from algotrade.core.model.errors import ConfigurationError
from algotrade.services.explore.ideas.ranking import NOT_PICKED, RULE_SCREEN_VALUES, VALUE_COLUMNS
from algotrade.services.explore.screens.results import RunRows, run_rows
from algotrade.services.explore.store import (
    NotFoundError,
    Page,
    ReadStore,
    cached,
    paginate,
)
from algotrade.services.explore.universe import ticker_columns
from algotrade.services.views import to_value

CHANGES = ("new", "dropped")
COLUMN_MODE = "column"  # a display column's rows in rule_screen_values (outcome INFO)
SORTS = ("rank", "score", "symbol", "name", "decision")
VALUES_BY_ID_LIMIT = 2000  # more tickers than this: read the whole partition, not row groups


@dataclass(frozen=True)
class CriterionHeader:
    criterion_id: str
    field: str
    mode: str  # hard / soft / score, as the spec states it


@dataclass(frozen=True)
class CriterionResult:
    value: float | str | None
    outcome: str  # PASS / NEAR / FAIL / MISSING


@dataclass(frozen=True)
class ScreenTableRow:
    rank: int  # 1 = best: score, then the tie-break, then the instrument id
    instrument_id: str
    symbol: str | None
    name: str | None
    decision: str
    score: float | None
    reasons: str
    flags: list[str]
    change: str | None  # new / dropped against the previous run (None: same, or no previous run)
    previous_decision: str | None  # None: no previous run, or the instrument was not in it
    criteria: dict[str, CriterionResult]  # criterion id -> what it judged
    columns: dict[str, Any]  # the screen's display columns
    features: dict[str, Any]  # the requested catalogue features, by name


@dataclass(frozen=True)
class ScreenTable:
    config_id: str
    user: str
    session: date
    previous_session: date | None  # None: the screen has no earlier stored run
    run_id: str
    decisions: dict[str, int]  # every decision of the run (before any filter)
    changes: dict[str, int]  # ``new`` / ``dropped`` counts (before any filter)
    criteria: list[CriterionHeader]  # spec order
    column_names: list[str]  # the screen's display columns, spec order
    feature_columns: list[str]  # the requested catalogue features, in order
    missing: list[str]  # tables with no partition for the session (their features are null)
    page: Page[ScreenTableRow]


@dataclass(frozen=True)
class _Computed:
    run: RunRows
    previous_session: date | None
    decisions: dict[str, int]
    changes: dict[str, int]
    criteria: list[CriterionHeader]
    column_names: list[str]
    missing: list[str]
    rows: list[ScreenTableRow]


def _text(value: object) -> str | None:
    out = to_value(value)
    return None if out is None else str(out)


def _picked(decision: str) -> bool:
    return decision not in NOT_PICKED


def _previous(store: ReadStore, config_id: str, session: date) -> RunRows | None:
    """The screen's run in the stored session before ``session`` (None: there is none)."""
    try:
        return run_rows(store, config_id, session - timedelta(days=1))
    except NotFoundError:
        return None


def _changes(
    now: pd.DataFrame, before: dict[str, str] | None
) -> dict[str, tuple[str | None, str | None]]:
    """``{instrument_id: (change, previous decision)}``; no previous run: no changes."""
    if before is None:
        return {}
    out: dict[str, tuple[str | None, str | None]] = {}
    for iid, decision in zip(now["instrument_id"], now["decision"], strict=True):
        was = before.get(str(iid))
        now_picked, was_picked = _picked(str(decision)), was is not None and _picked(was)
        out[str(iid)] = (
            "new" if now_picked and not was_picked else "dropped" if was_picked and not now_picked
            else None,
            was,
        )  # fmt: skip
    return out


def _values(
    store: ReadStore, run: RunRows, ids: list[str]
) -> tuple[dict[str, dict[str, CriterionResult]], dict[str, dict[str, Any]]]:
    """The stored per-criterion results and display columns of ``ids``, by instrument."""
    wanted = ids if len(ids) <= VALUES_BY_ID_LIMIT else None
    frame = store.reader.table_range(
        RULE_SCREEN_VALUES, run.session, run.session, None, wanted, VALUE_COLUMNS
    )
    criteria: dict[str, dict[str, CriterionResult]] = {}
    columns: dict[str, dict[str, Any]] = {}
    if frame is None or frame.empty:
        return criteria, columns
    frame = frame[
        (frame["user_id"] == run.owner)
        & (frame["config_id"] == run.config.config.id)
        & frame["instrument_id"].isin(set(ids))
    ]
    for r in frame.to_dict("records"):
        iid, cid = str(r["instrument_id"]), str(r["criterion_id"])
        num, text = to_value(r.get("value_num")), to_value(r.get("value_str"))
        value = num if num is not None else text
        if r["mode"] == COLUMN_MODE:
            columns.setdefault(iid, {})[cid] = value
        else:
            criteria.setdefault(iid, {})[cid] = CriterionResult(value, str(r["outcome"]))
    return criteria, columns


def _sort_key(row: ScreenTableRow, sort: str) -> Any:
    """The value a row is ordered by (None: no value, always last)."""
    if sort in SORTS:
        return getattr(row, sort)
    kind, _, name = sort.partition(":")
    if kind == "criterion":
        found = row.criteria.get(name)
        return None if found is None else found.value
    if kind == "column":
        return row.columns.get(name)
    return row.features.get(sort)


def _sorted(rows: list[ScreenTableRow], sort: str, known: set[str]) -> list[ScreenTableRow]:
    descending = sort.startswith("-")
    key = sort.removeprefix("-")
    kind, _, name = key.partition(":")
    ok = (
        key in SORTS
        or key in known
        or (kind == "criterion" and name != "")
        or (kind == "column" and name != "")
    )
    if not ok:
        raise ConfigurationError(f"sort: {key!r} is not a returned column")
    keyed = [(row, _sort_key(row, key)) for row in rows]
    have = [(r, v) for r, v in keyed if v is not None]
    lacking = [r for r, v in keyed if v is None]
    have.sort(
        key=lambda rv: (0, float(rv[1])) if isinstance(rv[1], int | float)
        else (1, str(rv[1]).casefold()),
        reverse=descending,
    )  # fmt: skip
    return [r for r, _ in have] + lacking


def _compute(
    store: ReadStore,
    config_id: str,
    on: date | None,
    decisions: tuple[str, ...],
    change: str | None,
    q: str | None,
    features: list[str],
    sort: str,
) -> _Computed:
    run = run_rows(store, config_id, on)
    if run.config.config.impl != RULES_IMPL:
        raise NotFoundError(f"{config_id} is not a rule screen: it has no criteria table")
    spec = run.config.screen_spec
    now = run.rows.sort_values("rank", kind="stable")
    prev = _previous(store, config_id, run.session)
    before = (
        None
        if prev is None
        else {
            str(i): str(d)
            for i, d in zip(prev.rows["instrument_id"], prev.rows["decision"], strict=True)
        }
    )
    moved = _changes(now, before)
    counts = now["decision"].astype(str).value_counts().to_dict()
    kept = now
    if decisions:
        kept = now[now["decision"].astype(str).str.casefold().isin(decisions)]
    if change:
        kept = kept[[moved.get(str(i), (None, None))[0] == change for i in kept["instrument_id"]]]
    ids = [str(i) for i in kept["instrument_id"]]
    extra = ticker_columns(store, run.session, features, ids)
    names = extra.frame.set_index(extra.frame["instrument_id"].astype(str))
    criteria, columns = _values(store, run, ids)
    rows = []
    for r in kept.to_dict("records"):
        iid = str(r["instrument_id"])
        info = names.loc[iid].to_dict() if iid in names.index else None
        symbol = None if info is None else _text(info["symbol"])
        name = None if info is None else _text(info["company_name"])
        if q and q.strip().casefold() not in f"{symbol or ''} {name or ''}".casefold():
            continue
        score = to_value(r.get("score"))
        flag_text = str(to_value(r.get("flags")) or "")
        rows.append(
            ScreenTableRow(
                rank=int(r["rank"]),
                instrument_id=iid,
                symbol=symbol,
                name=name,
                decision=str(r["decision"]),
                score=None if score is None else float(score),
                reasons=str(to_value(r.get("reasons")) or ""),
                flags=[f for f in flag_text.split(",") if f],
                change=moved.get(iid, (None, None))[0],
                previous_decision=moved.get(iid, (None, None))[1],
                criteria=criteria.get(iid, {}),
                columns=columns.get(iid, {}),
                features=(
                    {f: to_value(info[f]) for f in features} if info is not None
                    else dict.fromkeys(features)
                ),
            )
        )  # fmt: skip
    totals = pd.Series([c for c, _ in moved.values() if c]).value_counts().to_dict()
    return _Computed(
        run,
        None if prev is None else prev.session,
        {str(k): int(v) for k, v in counts.items()},
        {c: int(totals.get(c, 0)) for c in CHANGES} if before is not None else {},
        [CriterionHeader(c.id, c.field, c.mode.value) for c in spec.criteria],
        [name for name, _ in spec.columns],
        extra.missing,
        _sorted(rows, sort, set(features)),
    )


def screen_table(
    store: ReadStore,
    config_id: str,
    on: date | None,
    decisions: list[str],
    change: str | None,
    q: str | None,
    features: list[str],
    sort: str | None,
    page: int,
    size: int,
) -> ScreenTable:
    """The rows of ``config_id``'s latest run on or before ``on``: ``decisions`` (none listed:
    all), ``change`` (``new`` / ``dropped``) and the search ``q`` (ticker or name contains)
    filtered, ``features`` (catalogue field names) added, ordered by ``sort`` (``rank``,
    ``score``, ``symbol``, ``name``, ``decision``, ``criterion:<id>``, ``column:<name>`` or a
    requested feature; ``-`` prefix: descending; nulls last; default ``rank``), paged."""
    if change is not None and change not in CHANGES:
        raise ConfigurationError(f"change: {change!r} is not one of {', '.join(CHANGES)}")
    wanted = tuple(sorted({d.casefold() for d in decisions}))
    names = list(dict.fromkeys(features))
    order = sort or "rank"
    done = cached(
        store,
        ("screen_table", config_id, on, wanted, change, q, tuple(names), order),
        lambda: _compute(store, config_id, on, wanted, change, q, names, order),
    )
    return ScreenTable(
        config_id=config_id,
        user=done.run.owner,
        session=done.run.session,
        previous_session=done.previous_session,
        run_id=done.run.run_id,
        decisions=done.decisions,
        changes=done.changes,
        criteria=done.criteria,
        column_names=done.column_names,
        feature_columns=names,
        missing=done.missing,
        page=paginate(done.rows, page, size),
    )
