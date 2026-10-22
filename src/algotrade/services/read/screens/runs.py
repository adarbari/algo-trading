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

from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

import pandas as pd

from algotrade.services.read.availability.cause import Unavailable, run_cause
from algotrade.services.read.availability.unavailable import unavailable_tables
from algotrade.services.read.context import (
    DICT_BASE_BYTES,
    DICT_ENTRY_BYTES,
    NUMBER_BYTES,
    Held,
    ReadContext,
    at_session,
    partition,
    previous_session,
    run_rows_of,
    weigh,
)
from algotrade.services.read.values import Unknown, UnknownCode, to_scalar
from algotrade.services.screening.rule_results import NOT_PICKED, PAUSED, is_picked
from algotrade.storage.tables.schemas import result_table

RULE_SCREEN = result_table("rule_screen")
# ``run_summaries`` reads these (a ``ScreenerRun`` is built from them), column-pruned (the row key
# and the point-in-time columns come with them); ``run_rows`` reads ``RUN_COLUMNS`` of one run's
# own file, and ``load_results`` the heavier ``DETAIL_COLUMNS`` of the instruments a page asks for.
ROW_COLUMNS = ("user_id", "config_id", "config_version", "decision", "regime")
RUN_COLUMNS = ("user_id", "config_id", "config_version", "decision", "score", "rank", "tie_break",
               "regime")  # fmt: skip
DETAIL_COLUMNS = (
    "user_id", "config_id", "decision", "score", "rank", "tie_break", "flags", "reasons",
    "regime", "size_multiplier",
)  # fmt: skip

RunKey = tuple[str, str]  # (owner, config id)


def picked_mask(decisions: pd.Series) -> pd.Series:
    """``is_picked`` of every row at once (a run has thousands of rows: a Python loop over an
    Arrow column cost the ideas page a second)."""
    return ~decisions.astype(str).isin(NOT_PICKED)


@dataclass(frozen=True)
class DecisionCount:
    decision: str
    count: int


@dataclass(frozen=True)
class PickIds:
    """The picks of a run, in rank order (``instrument_ids``: at most the limit asked) and
    ``total``, how many it picked in all."""

    instrument_ids: tuple[str, ...]
    total: int


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
    ``missing_optional_tables``: the tables it ran without (no field needed them: ADR 0055; a
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


@dataclass(frozen=True)
class RunSummary:
    """What a screener's newest run says about itself in the rows it stored: its ``run_id``, when
    it was known, the version that ran, its decisions counted (most first) and the regime it
    stamped. The part of a ``ScreenerRun`` that comes from the rows, not from the run record."""

    run_id: str
    knowledge_ts: datetime
    config_version: int | None
    decisions: tuple[DecisionCount, ...]
    regime: str | None

    def weight_bytes(self) -> int:
        """About what it holds (``weigh``'s prices: strings, numbers, slots)."""
        return (
            weigh(self.run_id)
            + weigh(self.regime or "")
            + 3 * NUMBER_BYTES
            + sum(weigh(d.decision) + NUMBER_BYTES + DICT_BASE_BYTES for d in self.decisions)
        )


class RunSummaries:
    """The newest run of each (owner, config) for one publish (``run_summaries``): a few hundred
    bytes each, never the rows they were counted from."""

    def __init__(self, by_key: Mapping[RunKey, RunSummary]) -> None:
        self.by_key = by_key

    def weight_bytes(self) -> int:
        return sum(
            weigh(owner) + weigh(config) + s.weight_bytes() + DICT_ENTRY_BYTES
            for (owner, config), s in self.by_key.items()
        )


def run_summaries(ctx: ReadContext) -> RunSummaries | Unknown:
    """Each rule screen's newest run for the session, summarised once per publish and kept in
    ``ctx.cache`` (read first, ADR 0022): the rows it is counted from (``ROW_COLUMNS`` of every
    config's newest run, millions of rows on the real store) are dropped as soon as they are, so
    the cache holds a summary per screener, not a frame. ``Unknown``: no partition."""
    key = ("run_summaries", ctx.session.date, ctx.reader.own_run, ctx.reader.version())

    def build() -> RunSummaries | Unknown:
        stored = partition(ctx, RULE_SCREEN, ROW_COLUMNS, newest_runs=True)
        if isinstance(stored, Unknown):
            return stored
        return RunSummaries(
            {
                (str(o), str(c)): _summary(rows)
                for (o, c), rows in stored.groupby(["user_id", "config_id"], sort=False)
            }
        )

    found: RunSummaries | Unknown = ctx.cache.get_or_compute(key, build)
    return found


def _version(value: object) -> int | None:
    found = to_scalar(value)
    return None if found is None else int(found)


def _regime(rows: pd.DataFrame) -> str | None:
    """The label the run stamped (every row of a run carries the session's)."""
    if "regime" not in rows.columns:
        return None
    found = rows["regime"].dropna()  # every row carries it: the first stored one
    return str(found.iloc[0]) if not found.empty else None


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


def last_run_rows(rows: pd.DataFrame) -> tuple[pd.Series, pd.DataFrame]:
    """THE run-selection rule: of ``rows`` (one owner's rows of one config in one session) the
    run with the latest ``knowledge_ts`` (a later run supersedes an earlier one): its last
    row and every row of that run. ``pick_history`` applies the same rule per session."""
    last = rows.sort_values("knowledge_ts", kind="stable").iloc[-1]
    return last, rows[rows["run_id"] == str(last["run_id"])]


def _summary(rows: pd.DataFrame) -> RunSummary:
    """The summary of ``rows`` (one owner's rows of one config) by the latest-run rule."""
    last, mine = last_run_rows(rows)
    counts = mine["decision"].astype(str).value_counts()
    return RunSummary(
        run_id=str(last["run_id"]),
        knowledge_ts=pd.Timestamp(last["knowledge_ts"]).to_pydatetime(),
        config_version=_version(last.get("config_version")),
        decisions=tuple(
            DecisionCount(str(d), int(n))
            for d, n in sorted(counts.items(), key=lambda dn: (-int(dn[1]), str(dn[0])))
        ),
        regime=_regime(mine),
    )


def _run(ctx: ReadContext, owner: str, config_id: str, found: RunSummary) -> ScreenerRun:
    """The screener's run: its summary and its run record."""
    record = ctx.reader.run(found.run_id)
    stats: Mapping[str, Any] = {} if record is None else dict(record.stats)
    coverage, missing_tables, missing_optional = _coverage(stats)
    counts = {d.decision: d.count for d in found.decisions}
    return ScreenerRun(
        run_id=found.run_id,
        config_id=config_id,
        owner=owner,
        session=ctx.session.date,
        status=None if record is None else record.status.value,
        knowledge_ts=found.knowledge_ts,
        config_version=found.config_version,
        decisions=found.decisions,
        picked=sum(n for d, n in counts.items() if is_picked(d)),
        paused=counts.get(PAUSED, 0),
        regime=found.regime,
        audit=stats,
        coverage=coverage,
        missing_tables=missing_tables,
        missing_optional_tables=missing_optional,
        unavailable=unavailable_tables([*missing_tables, *missing_optional], ctx.session.date),
    )


def load_latest_runs(ctx: ReadContext, keys: Sequence[RunKey]) -> dict[RunKey, LatestRun]:
    """THE latest-run rule for each ``(owner, config id)`` of ``keys``, in one read."""
    day = ctx.session.date.isoformat()
    stored = run_summaries(ctx)
    if isinstance(stored, Unknown):
        why = Unknown(UnknownCode.NOT_RUN, stored.cause)
        return {k: LatestRun(None, why) for k in keys}
    out: dict[RunKey, LatestRun] = {}
    for owner, config_id in keys:
        found = stored.by_key.get((owner, config_id))
        if found is None:
            detail = f"{config_id} ({owner}) has no run in {RULE_SCREEN} for {day}"
            cause = run_cause(config_id, detail, ctx.session.date)
            out[(owner, config_id)] = LatestRun(None, Unknown(UnknownCode.NOT_RUN, cause))
        else:
            out[(owner, config_id)] = LatestRun(_run(ctx, owner, config_id, found), None)
    return out


def latest_run(ctx: ReadContext, owner: str, config_id: str) -> LatestRun:
    """``owner``'s run of ``config_id`` for the session, or ``NOT_RUN``."""
    return load_latest_runs(ctx, [(owner, config_id)])[(owner, config_id)]


RunRows = Held[pd.DataFrame]  # one publish's run rows (``run_rows``), a container per publish


def run_rows(ctx: ReadContext, run: ScreenerRun) -> pd.DataFrame:
    """The rows ``run`` stored (one per instrument; ``RUN_COLUMNS``), in rank order: read from the
    run's own file alone (``run_rows_of``, ADR 0064), not cut out of the session's every run, and
    sorted once per publish. They are kept in one ``RunRows`` in ``ctx.cache`` under the session,
    the view (``own_run``) and the published state read before computing (ADR 0022), shared by
    every request and only read by callers. The heavy columns (``reasons``, ``flags``) are read
    for the instruments a page asks for (``load_results``)."""
    key = ("run_rows", ctx.session.date, ctx.reader.own_run, ctx.reader.version())
    held: RunRows = ctx.cache.get_or_compute(key, RunRows)

    def read() -> pd.DataFrame:
        stored = run_rows_of(ctx, RULE_SCREEN, run.run_id, RUN_COLUMNS)
        mine = stored[(stored["user_id"] == run.owner) & (stored["config_id"] == run.config_id)]
        return mine.sort_values(["rank", "instrument_id"], kind="stable").reset_index(drop=True)

    rows, added = held.get_or_read(run.run_id, read)
    if added:
        ctx.cache.put(key, held)  # its weight changed: the cache bounds what it really holds
    return rows


def run_row_details(
    ctx: ReadContext, run: ScreenerRun, instruments: Collection[str]
) -> pd.DataFrame:
    """``run``'s rows of ``instruments`` with every column a result shows (``DETAIL_COLUMNS``:
    ``reasons`` and ``flags`` too), in rank order: read from the run's own file for those
    instruments only, never kept (a page asks for a few dozen of a run's thousands)."""
    stored = run_rows_of(ctx, RULE_SCREEN, run.run_id, DETAIL_COLUMNS, sorted(instruments))
    mine = stored[(stored["user_id"] == run.owner) & (stored["config_id"] == run.config_id)]
    return mine.sort_values(["rank", "instrument_id"], kind="stable").reset_index(drop=True)


def load_previous_run(ctx: ReadContext, run: ScreenerRun) -> ScreenerRun | None:
    """The same owner's run of ``run``'s screener in the previous stored session of
    ``results/rule_screen`` (by the latest-run rule there); None: no earlier session, or the
    screener did not run in it."""
    day = previous_session(ctx, RULE_SCREEN)
    if day is None:
        return None
    return latest_run(at_session(ctx, day), run.owner, run.config_id).run


def load_pick_ids(ctx: ReadContext, run: ScreenerRun, limit: int) -> PickIds:
    """The instrument ids of ``run``'s picks in rank order (at most ``limit``) and how many it
    picked in all: the picks and the picks the regime gate held back (``PAUSED``), read from
    the run's rows alone, never the criterion values behind them (the calendar needs who, not
    why; the values were the cost of a results page)."""
    rows = run_rows(ctx, run)
    decisions = rows["decision"]
    shown = rows[picked_mask(decisions) | (decisions.astype(str) == PAUSED)]
    ids = tuple(str(i) for i in shown["instrument_id"].iloc[: max(limit, 0)])
    return PickIds(ids, len(shown))
