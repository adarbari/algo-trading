"""The ``option-outcomes`` task (ADR 0053 amendment, EB H13; ADR 0088, design 2.5): write the
option trades of every window a session closes to ``outcomes/option/structure_pnl@v2``, the second
outcomes grain, which only the edge harness reads (``data.outcomes``).

For a window-end session T and each position of the site's open edge documents with an
``option_pnl`` outcome (``positions_wanted``: the outcome, each variant and each case point of a
case-valued parameter, for each hold h of its ``horizon_sessions``), S is the h-th exchange session
before T and the rows are the underlyings whose chain at S is ``OK``: the contracts chosen from S's
chain alone, the trade held to the first exit its rules give or to T (the option-structure engine,
``engines/structures/trades``; quotes and our own delta from each session's stored chain, never
filled from an earlier session), written to partition S under a ``position_key`` built from the
resolved legs (``config/edges/positions/key.py``). An exit rule over catalogue fields reads each
close's fields from that close's partition only (``option_fields``); a rule over a field the
window cannot read at all is REFUSED (recorded, the position's other windows and the other
positions still write, the check FAILs), as is ``skip_report_in_life`` until the earnings read
lands (E4b). A row's ``knowledge_ts`` is the latest chain and field partition read up to its own
exit; its ``licence`` the strictest of the price source and the rule's fields. A window whose S is
before the first stored chain is not computed (chains are stored from 2026-10-02); one whose T has
not closed is refused. Each night also recomputes the ``RECHECK`` window ends before it (a re-run
never retracts a row; its rows win per key), so a night's missed run is caught up.

``frame_and_publish`` is the one function that writes the table (G24): the owner-run history
writer (E5) computes frames and calls it.

The acceptance check (``check_option_outcomes``) holds the run to its own count: every underlying
with an ``OK`` chain at S has a row of each key, and the run's rows are stored; UNMEASURED rows are
counted by reason in the detail, never failures (a stale chain is a fact of the feed, ADR 0054); a
refused position FAILs.
"""

from collections.abc import Collection, Mapping
from dataclasses import dataclass
from datetime import date

import pandas as pd

from algotrade.config.edges.document import CLOSED, Edge, Outcome
from algotrade.config.edges.loading import load_edges
from algotrade.config.edges.positions.chain import CHAIN_KIND
from algotrade.config.edges.positions.key import case_points, position_key
from algotrade.config.edges.positions.spec import ExitRule, exit_rules
from algotrade.config.edges.positions.templates import Templates, load_templates
from algotrade.config.env import config_dir
from algotrade.config.site.settings import SourcesSettings
from algotrade.core.model.fields import is_position_field
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
from algotrade.engines.structures.chain import DayChain
from algotrade.engines.structures.trades import select_window, walk_trades
from algotrade.features.expressions.feature_set import FeatureSet
from algotrade.features.framework.feature import strictest
from algotrade.features.rollups.positioning.chain_inputs import closing_spots, one_row_per_contract
from algotrade.features.site import site_features
from algotrade.services.licences import licence_of
from algotrade.storage.configs.files import FileConfigStore
from algotrade.storage.runs import RunRecord, RunStatus
from algotrade.storage.tables.schemas import STRUCTURE_PNL, spec_for
from algotrade.storage.tables.spec import COMMON
from algotrade_ingestion.tasks.derived.option_fields import FieldLoader, refuse_unstored
from algotrade_ingestion.tasks.derived.option_paths import position_rows
from algotrade_ingestion.tasks.framework.run import IngestRun, TaskContext
from algotrade_ingestion.tasks.maintenance.quality import Check

TASK = "option-outcomes"
SOURCE = "option_outcomes"
TABLE = STRUCTURE_PNL
TABLES = (TABLE,)
PRICE_SOURCE = "cboe"  # this writer's chains; the licence of Cboe's open quotes is open
RECHECK = 2  # the window ends before a night's that it recomputes (a missed night is caught up)
SHOWN = 5  # reasons listed per window in the run stats
QUOTE_COLUMNS = (
    "instrument_id", "underlying_id", "expiry", "right", "strike", "bid", "ask", "open_interest",
    "ts",
)  # fmt: skip
SITE = FileConfigStore(config_dir())


@dataclass(frozen=True)
class Wanted:
    """One position to write for a window ending at a night: the outcome (a document's, a
    variant's or a case point's) held at most ``hold`` sessions, its stored ``key``, its ordered
    exit ``rules`` and the catalogue ``fields`` they name."""

    outcome: Outcome
    hold: int
    key: str
    rules: tuple[ExitRule, ...]
    fields: tuple[str, ...]


def positions_wanted(edges: Collection[Edge], templates: Templates) -> list[Wanted]:
    """Every position of the open edge documents' (and ``[[variants]]``') ``option_pnl`` outcomes
    and their case points, for each hold of its ``horizon_sessions``, by key (a new edge needs no
    code change; two setups that resolve to one key share its rows)."""
    outcomes = [
        o
        for e in edges
        if e.status not in CLOSED
        for o in (e.outcome, *(v.outcome for v in e.variants))
    ]
    found: dict[str, Wanted] = {}
    for outcome in outcomes:
        if outcome.kind != CHAIN_KIND or outcome.position is None:
            continue
        for point in case_points(outcome, templates):
            rules = exit_rules(point.position.exit if point.position else None)
            names = {
                r.field for x in rules for r in x.rule.rules() if not is_position_field(r.field)
            }
            for hold in point.horizon_sessions:
                key = position_key(point, hold)
                found[key] = Wanted(point, hold, key, rules, tuple(sorted(names)))
    return sorted(found.values(), key=lambda w: (w.hold, w.key))


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
    configs = ctx.configs or SITE
    wanted = positions_wanted(load_edges(configs), load_templates(configs))
    stored = ctx.reader.dates(CHAIN_STATUS)
    first = stored[0] if stored else ends[-1]
    loader = ChainLoader(ctx.reader, ctx.settings)
    fields = FieldLoader(ctx.reader)
    features = site_features(configs) if any(w.fields for w in wanted) else None
    record: RunRecord | None = None
    for t in ends:
        record = _one(ctx, t, wanted, first, loader, fields, features)
    assert record is not None
    return record


def _licence(features: FeatureSet | None, fields: tuple[str, ...]) -> str:
    """The strictest licence of Cboe's open quotes and the exit rule's catalogue fields."""
    held = [] if features is None else [licence_of(features, f) for f in fields]
    return strictest(["open", *held])


def trade_rows(
    w: Wanted,
    sessions: list[date],
    loader: ChainLoader,
    fields: FieldLoader,
    licence: str,
) -> tuple[pd.DataFrame, int]:
    """The ``structure_pnl@v2`` rows of position ``w`` for the window ``sessions`` (S..T in
    order) -> (rows, the number of names with an ``OK`` chain at S). The chain of S is read whole,
    the later sessions' only for the contracts the entry chose; each close's rule fields come from
    that close's own partition."""
    spec = w.outcome.position
    assert spec is not None
    entry = loader(sessions[0], None)
    selected = select_window(
        entry, spec.legs, int(w.outcome.tenor_days or 0), spec.expiry_cycle, sessions[-1]
    )
    held = {c.instrument_id for sel in selected.values() for c in sel.legs}
    days = [entry, *(loader(d, held) for d in sessions[1:])]
    names = sorted(n for n, sel in selected.items() if sel.reason is None)
    catalogue, stamps = [], [entry.known]
    for day in days[1:]:
        values, field_known = fields(day.day, w.fields, names)
        catalogue.append(values)
        stamps.append(max((x for x in (day.known, field_known) if x is not None), default=None))
    trades = walk_trades(days, spec.legs, spec.collateral, selected, w.rules, catalogue, spec.book)
    rows = position_rows(
        trades, stamps, key=w.key, hold=w.hold, window_end=sessions[-1], price_source=PRICE_SOURCE,
        licence=licence, ts=close_time(sessions[0]),
    )  # fmt: skip
    return rows, len(selected)


def _one(
    ctx: TaskContext,
    end: date,
    wanted: list[Wanted],
    first: date,
    loader: ChainLoader,
    fields: FieldLoader,
    features: FeatureSet | None,
) -> RunRecord:
    current: date | None = None
    parts: dict[date, list[pd.DataFrame]] = {}  # one partition per start session, written once
    with IngestRun(ctx, TASK, end) as run:
        for w in wanted:
            sessions = sessions_ending(end, w.hold + 1)
            if sessions[0] < first:
                run.record_item(w.key, "BEFORE_HISTORY")
                continue
            refusal = _refusal(ctx.reader, w, sessions)
            if refusal:
                run.record_item(w.key, f"REFUSED: {refusal}")
                run.stats[w.key] = {"refused": refusal}
                continue
            if sessions[0] != current:
                loader.reset()  # the previous hold's entry chain is not this one's
                current = sessions[0]
            rows, ok = trade_rows(w, sessions, loader, fields, _licence(features, w.fields))
            if len(rows):
                parts.setdefault(sessions[0], []).append(rows)
            reasons = rows.loc[rows["outcome_status"] == "UNMEASURED", "outcome_reason"]
            run.record_item(w.key, f"OK: {len(rows)} rows")
            run.stats[w.key] = {
                "start": sessions[0].isoformat(),
                "rows": len(rows),
                "ok_chains": ok,
                "unmeasured": len(reasons),
                "unknown_closes": int(rows["exit_unknown_closes"].sum()),
                "reasons": {
                    str(r).split(":")[0]: int(n) for r, n in reasons.value_counts().items()
                },
            }
        frame_and_publish(run, parts)
        loader.reset()
    return run.record


def _refusal(reader: StoreReader, w: Wanted, sessions: list[date]) -> str:
    """Why position ``w`` is not written for the window ``sessions`` ('' when it is)."""
    spec = w.outcome.position
    if spec is not None and spec.skip_report_in_life:
        return "skip_report_in_life needs the expected-report read (a later slice)"
    problems = refuse_unstored(reader, w.fields, sessions[1:])
    return "; ".join(problems[:SHOWN])


DECLARED = tuple(c.name for c in spec_for(TABLE).columns if c.name not in COMMON)  # + the stamps


def frame_and_publish(run: IngestRun, parts: Mapping[date, list[pd.DataFrame]]) -> None:
    """Write the trade frames of each start session as one partition of ``structure_pnl@v2``: the
    one publisher of the table (G24; the history writer calls it too). Each frame must carry
    exactly the table's declared columns (``knowledge_ts`` per row beside them); the frames of one
    session are joined (a second write would replace the partition's first), ``knowledge_ts`` is
    taken from the rows, never the write time."""
    for start, frames in sorted(parts.items()):
        both = pd.concat(frames, ignore_index=True)
        wanted = {*DECLARED, "knowledge_ts"}
        missing, extra = sorted(wanted - set(both.columns)), sorted(set(both.columns) - wanted)
        if missing or extra:
            raise ValueError(f"{TABLE} frame for {start}: missing {missing}, undeclared {extra}")
        stamps = both.pop("knowledge_ts")
        run.write(TABLE, both, SOURCE, session=start, known=stamps)


def check_option_outcomes(reader: StoreReader, session: date, s: SourcesSettings) -> list[Check]:
    """The acceptance of the ``option-outcomes`` step for window end ``session``: for each
    position window the run computed, every underlying with an ``OK`` chain at S (counted again
    here from the stored status) has a row of that ``position_key``, and the run's rows are
    stored; a position the run refused fails."""
    runs = [r for r in reader.runs(TASK, session) if r.status == RunStatus.COMPLETE]
    if not runs:
        return [Check("option_outcomes", "FAIL", f"no complete option-outcomes run for {session}")]
    problems: list[str] = []
    unmeasured = 0
    windows = 0
    for key, value in sorted(runs[-1].stats.items()):
        if not isinstance(value, dict):
            continue
        if "refused" in value:
            problems.append(f"{key[:60]}: refused ({value['refused']})")
            continue
        if "start" not in value:
            continue
        windows += 1
        start = date.fromisoformat(value["start"])
        status = chain_status(reader, start)
        ok = 0
        if status is not None and not status.empty:
            labels = chain_labels(status, start, s.max_chain_stale_sessions)
            ok = int((labels == OK_LABEL).sum())
        part = reader.table(TABLE, start)
        mine = 0
        if part is not None:
            mine = int(
                (
                    (pd.to_datetime(part["window_end"]).dt.date == session)
                    & (part["position_key"] == key)
                ).sum()
            )
        if ok != value["rows"] or mine != value["rows"]:
            problems.append(
                f"{key[:60]}: {ok} OK chains at {start}, {value['rows']} rows, {mine} stored"
            )
        unmeasured += int(value["unmeasured"])
    if problems:
        return [Check("option_outcomes", "FAIL", "; ".join(problems[:SHOWN]))]
    return [
        Check(
            "option_outcomes", "PASS",
            f"{windows} position windows closed by {session}, every OK chain has a row; "
            f"{unmeasured} UNMEASURED (a chain missing or stale)",
        )
    ]  # fmt: skip
