"""The ``option-outcomes`` task (ADR 0053 amendment, EB H13): write the chain P&L of every window
a session closes to ``outcomes/option/structure_pnl@v1``, the second outcomes grain, which only
the edge harness reads (``data.outcomes``).

For a window-end session T and each (structure, tenor rule, horizon h) the site's open edge
documents with an ``option_pnl`` outcome name (``config.edges``), S is the h-th exchange session
before T and the rows are the underlyings whose chain at S is ``OK``: what the structure bought at
S's close and sold at T's earned (``option_paths``, quotes and our own delta from each session's
stored chain, never filled from an earlier session), written to partition S. ``knowledge_ts`` is
the latest ``knowledge_ts`` among the chain partitions the window read, not the write time. A
window whose S is before the first stored chain is not computed (chains are stored from
2026-10-02: the grain is forward-only, no backfill); one whose T has not closed is refused. Each
night also recomputes the ``RECHECK`` window ends before it (a re-run never retracts a row; its
rows win per key), so a night's missed run is caught up.

The acceptance check (``check_option_outcomes``) holds the run to its own count: every underlying
with an ``OK`` chain at S has a row, and the run's rows are stored; UNMEASURED rows are counted by
reason in the detail, never failures (a stale chain is a fact of the feed, ADR 0054).
"""

from collections.abc import Collection
from datetime import date

import pandas as pd

from algotrade.config.edges.document import CLOSED
from algotrade.config.edges.loading import Documents, load_edges
from algotrade.config.edges.positions.chain import CHAIN_KIND, grain_structure
from algotrade.config.env import config_dir
from algotrade.config.site.settings import SourcesSettings
from algotrade.core.time.calendar import close_time, sessions_between, sessions_ending
from algotrade.data import StoreReader
from algotrade.data.chains import (
    CHAIN_STATUS,
    OK_LABEL,
    chain_labels,
    chain_status,
    option_quote_rows,
    underlying_quotes,
)
from algotrade.features.rollups.positioning.chain_inputs import closing_spots, one_row_per_contract
from algotrade.storage.configs.files import FileConfigStore
from algotrade.storage.runs import RunRecord, RunStatus
from algotrade.storage.tables.schemas import OPTION_PNL
from algotrade_ingestion.tasks.derived.option_paths import DayChain, structure_rows
from algotrade_ingestion.tasks.framework.run import IngestRun, TaskContext
from algotrade_ingestion.tasks.maintenance.quality import Check

TASK = "option-outcomes"
SOURCE = "option_outcomes"
TABLE = OPTION_PNL
TABLES = (TABLE,)
RECHECK = 2  # the window ends before a night's that it recomputes (a missed night is caught up)
SHOWN = 5  # reasons listed per window in the run stats
QUOTE_COLUMNS = ("instrument_id", "underlying_id", "expiry", "right", "strike", "bid", "ask", "ts")
SITE = FileConfigStore(config_dir())


def windows_wanted(configs: Documents | None = None) -> list[tuple[str, int, int]]:
    """The ``(grain structure, tenor_days, horizon_sessions)`` of every open edge document's (and
    ``[[variants]]``') ``option_pnl`` outcome, sorted: a new edge needs no code change."""
    edges = [e for e in load_edges(configs or SITE) if e.status not in CLOSED]
    outcomes = [o for e in edges for o in (e.outcome, *(v.outcome for v in e.variants))]
    return sorted(
        {
            (grain_structure(o.structure or "", o.strike_delta), int(o.tenor_days or 0), h)
            for o in outcomes
            if o.kind == CHAIN_KIND
            for h in o.horizon_sessions
        }
    )


class ChainLoader:
    """The chains of sessions as ``DayChain``s from the store, the entry session's cached while
    its structures are computed (``reset`` drops it)."""

    def __init__(self, reader: StoreReader, sources: SourcesSettings) -> None:
        self.reader, self.sources = reader, sources
        self._entry: dict[date, DayChain] = {}
        self._days: dict[date, tuple[dict[str, str], dict[str, float], list[pd.Timestamp]]] = {}

    def reset(self) -> None:
        self._entry.clear()

    def _day(self, day: date) -> tuple[dict[str, str], dict[str, float], list[pd.Timestamp]]:
        """A session's chain labels, closing quotes and partition stamps, read once a run (the
        status and the quotes serve every window that touches the session)."""
        if day in self._days:
            return self._days[day]
        status = chain_status(self.reader, day)
        labels: dict[str, str] = {}
        stamps: list[pd.Timestamp] = []
        if status is not None and not status.empty:
            labelled = chain_labels(status, day, self.sources.max_chain_stale_sessions)
            labels = dict(
                zip(status["instrument_id"].astype(str), labelled.astype(str), strict=True)
            )
            stamps.append(pd.Timestamp(status["knowledge_ts"].max()))
        quotes = underlying_quotes(self.reader, day)
        spots: dict[str, float] = {}
        if quotes is not None and not quotes.empty:
            spots = {str(i): float(v) for i, v in closing_spots(quotes).items()}  # the closes
            stamps.append(pd.Timestamp(quotes["knowledge_ts"].max()))
        self._days[day] = labels, spots, stamps
        return self._days[day]

    def __call__(self, day: date, ids: Collection[str] | None) -> DayChain:
        if ids is None and day in self._entry:
            return self._entry[day]
        labels, spots, base = self._day(day)
        stamps = list(base)
        held = None if ids is not None and not ids else ids  # no contract held: none to read
        options = (
            None
            if ids is not None and not ids
            else option_quote_rows(self.reader, day, held, (*QUOTE_COLUMNS, "knowledge_ts"))
        )
        if options is not None and not options.empty:
            stamps.append(pd.Timestamp(options["knowledge_ts"].max()))
            options = one_row_per_contract(options).drop(columns=["knowledge_ts", "ts"])
            options = options.assign(underlying_id=options["underlying_id"].astype(str))
        known = max(stamps).to_pydatetime() if stamps else None
        chain = DayChain(day, options, spots, labels, known)
        if ids is None:
            self._entry[day] = chain
        return chain


def compute_option_outcomes(
    ctx: TaskContext, session: date, start: date | None = None, end: date | None = None
) -> RunRecord:
    """The windows ``session`` and the ``RECHECK`` sessions before it close, or those of every
    window-end session in ``start..end`` (one run each) -> the last run's record."""
    ends = (
        sessions_between(start, end or session) if start else sessions_ending(session, RECHECK + 1)
    )
    if not ends:
        raise ValueError(f"no exchange session in {start}..{end or session}")
    if close_time(ends[-1]) > ctx.clock():
        raise ValueError(f"the window ending {ends[-1]} has not closed yet")
    wanted = windows_wanted(ctx.configs)
    stored = ctx.reader.dates(CHAIN_STATUS)
    first = stored[0] if stored else ends[-1]
    loader = ChainLoader(ctx.reader, ctx.settings)
    record: RunRecord | None = None
    for t in ends:
        record = _one(ctx, t, wanted, first, loader)
    assert record is not None
    return record


def _one(
    ctx: TaskContext,
    end: date,
    wanted: list[tuple[str, int, int]],
    first: date,
    loader: ChainLoader,
) -> RunRecord:
    current: date | None = None
    parts: dict[date, list[pd.DataFrame]] = {}  # one partition per start session, written once
    with IngestRun(ctx, TASK, end) as run:
        for structure, tenor, h in sorted(wanted, key=lambda w: w[2]):
            key = f"{structure}:t{tenor}:h{h}"
            sessions = sessions_ending(end, h + 1)
            if sessions[0] < first:
                run.record_item(key, "BEFORE_HISTORY")
                continue
            if sessions[0] != current:
                loader.reset()  # the previous horizon's entry chain is not this one's
                current = sessions[0]
            rows, known = structure_rows(sessions, loader, structure, tenor, h)
            if len(rows):
                stamp = known if known is not None else ctx.clock()
                parts.setdefault(sessions[0], []).append(
                    rows.assign(ts=close_time(sessions[0]), knowledge_ts=pd.Timestamp(stamp))
                )
            reasons = rows.loc[rows["outcome_status"] == "UNMEASURED", "outcome_reason"]
            run.record_item(key, f"OK: {len(rows)} rows")
            run.stats[key] = {
                "start": sessions[0].isoformat(),
                "rows": len(rows),
                "unmeasured": len(reasons),
                "hedge_missing": int(rows["hedge_reason"].notna().sum()),
                "reasons": {
                    str(r).split(":")[0]: int(n) for r, n in reasons.value_counts().items()
                },
            }
        for start, frames in parts.items():
            # same-horizon windows share S: a second write would replace the first partition
            both = pd.concat(frames, ignore_index=True)
            stamps = both.pop("knowledge_ts")
            run.write(TABLE, both, SOURCE, session=start, known=stamps)
        loader.reset()
    return run.record


def check_option_outcomes(reader: StoreReader, session: date, s: SourcesSettings) -> list[Check]:
    """The acceptance of the ``option-outcomes`` step for window end ``session``: for each
    window the run computed, every underlying with an ``OK`` chain at S (counted again here from
    the stored status) has a row, and the run's rows are stored."""
    runs = [r for r in reader.runs(TASK, session) if r.status == RunStatus.COMPLETE]
    if not runs:
        return [Check("option_outcomes", "FAIL", f"no complete option-outcomes run for {session}")]
    problems: list[str] = []
    unmeasured = 0
    windows = 0
    for key, value in sorted(runs[-1].stats.items()):
        if not isinstance(value, dict) or "start" not in value:
            continue
        windows += 1
        start = date.fromisoformat(value["start"])
        status = chain_status(reader, start)
        ok = 0
        if status is not None and not status.empty:
            labels = chain_labels(status, start, s.max_chain_stale_sessions)
            ok = int((labels == OK_LABEL).sum())
        structure, tenor, horizon = key.split(":")
        part = reader.table(TABLE, start)
        mine = 0
        if part is not None:
            mine = int(
                (
                    (pd.to_datetime(part["window_end"]).dt.date == session)
                    & (part["structure"] == structure)
                    & (part["tenor_days"] == int(tenor.removeprefix("t")))
                    & (part["horizon_sessions"] == int(horizon.removeprefix("h")))
                ).sum()
            )
        if ok != value["rows"] or mine != value["rows"]:
            problems.append(
                f"{key}: {ok} OK chains at {start}, {value['rows']} rows, {mine} stored"
            )
        unmeasured += int(value["unmeasured"])
    if problems:
        return [Check("option_outcomes", "FAIL", "; ".join(problems[:SHOWN]))]
    return [
        Check(
            "option_outcomes", "PASS",
            f"{windows} windows closed by {session}, every OK chain has a row; "
            f"{unmeasured} UNMEASURED (a chain missing or stale)",
        )
    ]  # fmt: skip
