"""A screener's run for the session (``ScreenerRun``) and THE latest-run rule (ADR 0036): the
rows a screener's owner stored in ``results/rule_screen`` for exactly ``ctx.session.date``,
of the run with the latest ``knowledge_ts`` (a later run of the same session supersedes an
earlier one). No run stored for the session is ``NOT_RUN``; an older session's run is never
shown (the Ideas 20-session lookback is gone: owner decision, docs/api/read-model.md).

A ticker is *picked* when its decision is not in ``NOT_PICKED`` (REJECT, SKIPPED, UNKNOWN,
EXCLUDED, a stale chain the chains gate tolerated, ADR 0054; PAUSED: a pick the regime gate
held back is counted in ``ScreenerRun.paused``, never in ``picked``, ADR 0049);
``ScreenerRun.decisions``, ``picked`` and ``paused`` count the whole
run, never a page of it. A run is
compared with the screener's run in the previous stored session of ``results/rule_screen``
(``load_previous_run``: that date is named explicitly through ``context.previous_session``,
and the same latest-run rule applies there)."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

import pandas as pd

from algotrade.services.read.availability.cause import Unavailable, run_cause
from algotrade.services.read.availability.unavailable import unavailable_tables
from algotrade.services.read.context import ReadContext, at_session, partition, previous_session
from algotrade.services.read.values import Unknown, UnknownCode, to_scalar
from algotrade.storage.tables.schemas import result_table

RULE_SCREEN = result_table("rule_screen")
# Read column-pruned (the row key and the point-in-time columns come with them).
ROW_COLUMNS = (
    "user_id", "config_id", "config_version", "decision", "score", "rank", "tie_break", "flags",
    "reasons", "regime", "size_multiplier",
)  # fmt: skip
PAUSED = "PAUSED"  # the regime gate held the pick back (ADR 0049)
EXCLUDED = "EXCLUDED"  # a stale chain the chains gate tolerated (ADR 0054): never a pick
NOT_PICKED = frozenset({"REJECT", "SKIPPED", "UNKNOWN", PAUSED, EXCLUDED})

RunKey = tuple[str, str]  # (owner, config id)


def is_picked(decision: str) -> bool:
    """Whether a row with ``decision`` is one of the screener's picks."""
    return decision not in NOT_PICKED


@dataclass(frozen=True)
class DecisionCount:
    decision: str
    count: int


@dataclass(frozen=True)
class ScreenerRun:
    """One screener's run for the session. ``status``: its run record's (COMPLETE, PARTIAL,
    ...; None: no record stored); ``config_version``: the version that ran; ``decisions``:
    every decision of the run with its count (most first); ``picked``: the tickers it picked;
    ``paused``: the picks the regime gate held back; ``regime``: the session's label the run
    stamped on its rows (None: gate off, unknown, or a run before the stamp); ``audit``: its
    run record's stats (coverage, the selection's audit; empty: no record); ``coverage``: the
    record's coverage (COMPLETE, PARTIAL; None: not recorded) and ``missing_tables``: the
    tables that had no rows when it ran (its own, not the session's as read now);
    ``missing_optional_tables``: the optional sources' tables it ran without (ADR 0055: a
    COMPLETE run, warned not failed)."""

    run_id: str
    config_id: str
    owner: str
    session: date
    status: str | None
    knowledge_ts: datetime
    config_version: int | None
    decisions: tuple[DecisionCount, ...]
    picked: int
    paused: int
    regime: str | None
    audit: Mapping[str, Any]
    coverage: str | None = None
    missing_tables: tuple[str, ...] = ()
    missing_optional_tables: tuple[str, ...] = ()
    unavailable: tuple[Unavailable, ...] = ()  # what those tables leave out (ADR 0056)


@dataclass(frozen=True)
class LatestRun:
    """A screener's run for the session, or why it has none (``not_run``: ``NOT_RUN``)."""

    run: ScreenerRun | None
    not_run: Unknown | None


def screen_rows(ctx: ReadContext) -> pd.DataFrame | Unknown:
    """Every rule screen's rows for the session (column-pruned), read once per publish."""
    key = ("rule_screen", ctx.session.date, ctx.reader.own_run, ctx.reader.visible_seq())
    found: pd.DataFrame | Unknown | None = ctx.cache.get(key)  # key read first (ADR 0022)
    if found is None:
        found = partition(ctx, RULE_SCREEN, ROW_COLUMNS)
        ctx.cache.put(key, found)
    return found


def _version(value: object) -> int | None:
    found = to_scalar(value)
    return None if found is None else int(found)


def _regime(rows: pd.DataFrame) -> str | None:
    """The label the run stamped (every row of a run carries the session's)."""
    if "regime" not in rows.columns:
        return None
    found = [str(r) for r in rows["regime"] if to_scalar(r) is not None]
    return found[0] if found else None


def _tables(stats: Mapping[str, Any], key: str) -> tuple[str, ...]:
    return tuple(sorted(str(t) for t in stats.get(key) or ()))


def _coverage(stats: Mapping[str, Any]) -> tuple[str | None, tuple[str, ...], tuple[str, ...]]:
    """The run record's coverage, the tables it ran without (``stats["missing_tables"]``) and
    the optional ones (``stats["missing_optional_tables"]``)."""
    coverage = stats.get("coverage")
    return (
        None if coverage is None else str(coverage),
        _tables(stats, "missing_tables"),
        _tables(stats, "missing_optional_tables"),
    )


def _run(ctx: ReadContext, owner: str, config_id: str, rows: pd.DataFrame) -> ScreenerRun:
    """The run of ``rows`` (one owner's rows of one config) with the latest ``knowledge_ts``."""
    last = rows.sort_values("knowledge_ts", kind="stable").iloc[-1]
    run_id = str(last["run_id"])
    mine = rows[rows["run_id"] == run_id]
    counts = mine["decision"].astype(str).value_counts()
    record = ctx.reader.run(run_id)
    stats: Mapping[str, Any] = {} if record is None else dict(record.stats)
    coverage, missing_tables, missing_optional = _coverage(stats)
    return ScreenerRun(
        run_id=run_id,
        config_id=config_id,
        owner=owner,
        session=ctx.session.date,
        status=None if record is None else record.status.value,
        knowledge_ts=pd.Timestamp(last["knowledge_ts"]).to_pydatetime(),
        config_version=_version(last.get("config_version")),
        decisions=tuple(
            DecisionCount(str(d), int(n))
            for d, n in sorted(counts.items(), key=lambda dn: (-int(dn[1]), str(dn[0])))
        ),
        picked=int(sum(int(n) for d, n in counts.items() if is_picked(str(d)))),
        paused=int(counts.get(PAUSED, 0)),
        regime=_regime(mine),
        audit=stats,
        coverage=coverage,
        missing_tables=missing_tables,
        missing_optional_tables=missing_optional,
        unavailable=unavailable_tables([*missing_tables, *missing_optional], ctx.session.date),
    )


def load_latest_runs(ctx: ReadContext, keys: Sequence[RunKey]) -> dict[RunKey, LatestRun]:
    """THE latest-run rule for each ``(owner, config id)`` of ``keys``, in one read."""
    day = ctx.session.date.isoformat()
    stored = screen_rows(ctx)
    if isinstance(stored, Unknown):
        why = Unknown(UnknownCode.NOT_RUN, stored.cause)
        return {k: LatestRun(None, why) for k in keys}
    groups = {
        (str(o), str(c)): rows
        for (o, c), rows in stored.groupby(["user_id", "config_id"], sort=False)
    }
    out: dict[RunKey, LatestRun] = {}
    for owner, config_id in keys:
        rows = groups.get((owner, config_id))
        if rows is None:
            detail = f"{config_id} ({owner}) has no run in {RULE_SCREEN} for {day}"
            cause = run_cause(config_id, detail, ctx.session.date)
            out[(owner, config_id)] = LatestRun(None, Unknown(UnknownCode.NOT_RUN, cause))
        else:
            out[(owner, config_id)] = LatestRun(_run(ctx, owner, config_id, rows), None)
    return out


def latest_run(ctx: ReadContext, owner: str, config_id: str) -> LatestRun:
    """``owner``'s run of ``config_id`` for the session, or ``NOT_RUN``."""
    return load_latest_runs(ctx, [(owner, config_id)])[(owner, config_id)]


def run_rows(ctx: ReadContext, run: ScreenerRun) -> pd.DataFrame:
    """The rows ``run`` stored (one per instrument), in rank order. Filtering the session's
    whole partition for a run is the cost, and a page asks for each run's rows several times:
    kept in the request's ``ctx.memo`` (read only by callers)."""
    key = ("run_rows", ctx.session.date, run.owner, run.config_id, run.run_id)
    found: pd.DataFrame | None = ctx.memo.get(key)
    if found is None:
        stored = screen_rows(ctx)
        if isinstance(stored, Unknown):  # pragma: no cover - the run was found in these rows
            return pd.DataFrame(columns=["instrument_id", *ROW_COLUMNS])
        mine = stored[
            (stored["user_id"] == run.owner)
            & (stored["config_id"] == run.config_id)
            & (stored["run_id"] == run.run_id)
        ]
        found = mine.sort_values(["rank", "instrument_id"], kind="stable").reset_index(drop=True)
        ctx.memo[key] = found
    return found


def load_previous_run(ctx: ReadContext, run: ScreenerRun) -> ScreenerRun | None:
    """The same owner's run of ``run``'s screener in the previous stored session of
    ``results/rule_screen`` (by the latest-run rule there); None: no earlier session, or the
    screener did not run in it."""
    day = previous_session(ctx, RULE_SCREEN)
    if day is None:
        return None
    return latest_run(at_session(ctx, day), run.owner, run.config_id).run
