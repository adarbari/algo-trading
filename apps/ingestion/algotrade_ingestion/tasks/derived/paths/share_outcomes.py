"""The ``share-outcomes`` task (ADR 0088, E3c-2): write the share trades of every window a session
closes to ``outcomes/instrument/share_path@v1``, which only the edge harness reads
(``data.outcomes``).

For a window-end session T and each share position of the site's open edge documents that declares
an ``[outcome.exit]`` (``wanted.positions_wanted(..., SHARES)``: each variant and case point, for
each hold h of its ``horizon_sessions``), S is the h-th exchange session before T and the rows are
the names in the universe at S with a bar at S (as the ``outcomes`` task counts them): each walked
over the closes of S..T (split-adjusted as of T) to the first exit its ordered rules give or to T by
the share path walker (``engines/structures/share_walk``), written to partition S under the
position's ``share_position_key`` and its outcome's benchmark (the benchmark's return over S..exit
beside the name's; ``none``: null). An exit rule over catalogue fields reads each close's fields
from that close's own partition only (``close_fields``); a rule over a field the window cannot read
at all is REFUSED (recorded, the position's other windows and the other positions still write, the
check FAILs), never run as a rule that never fires. A name with no close before its exit is
UNMEASURED (``BAD_BAR`` when the first missing close is a flagged bar, else ``NO_BAR``), unless the
reference or the listing history says it left (DELISTED at its last close). A row's ``knowledge_ts``
is the latest bars and field partition read up to its own exit; a DELISTED or UNMEASURED row's is
the write time (the delisting is noticed later than its last bar), as is a stored row's that a
recheck changes (a cleared flag, a late split); its ``licence`` the strictest of the bars' and the
rule's fields.

Each night also recomputes the ``RECHECK`` window ends before it (the ``outcomes`` task's, so a
delisting noticed by the weekly reference build turns a ``NO_BAR`` row into a DELISTED one) and
writes only the rows that are new or changed (``changed_rows``): a re-run that changes nothing
writes nothing, and an unchanged row keeps its first-known stamp. A window whose S is before the
first stored bars session is not computed; one whose T has not closed is refused.

The acceptance check (``check_share_outcomes``) holds the run to its own count: every name in the
universe at S with a bar at S has a row of each key the run computed, and they are stored; a
refused position FAILs."""

import math
from collections.abc import Mapping, Sequence
from datetime import date, datetime

import pandas as pd

from algotrade.config.edges.loading import load_edges
from algotrade.config.edges.positions.templates import SHARES, load_templates
from algotrade.config.env import config_dir
from algotrade.config.site.settings import SourcesSettings
from algotrade.core.time.calendar import close_time, sessions_between, sessions_ending
from algotrade.data import StoreReader
from algotrade.data.prices import SessionBars, bar_stamps, session_bars
from algotrade.engines.structures.share_walk import ShareClose, ShareWalk, walk_share
from algotrade.features.expressions.feature_set import FeatureSet
from algotrade.features.site import site_features
from algotrade.storage.configs.files import FileConfigStore
from algotrade.storage.runs import RunRecord, RunStatus
from algotrade.storage.tables.schemas import SHARE_PATH, UNMEASURED, spec_for
from algotrade.storage.tables.spec import COMMON
from algotrade_ingestion.tasks.derived.outcome_paths import BAD_BAR, Window, wide_closes
from algotrade_ingestion.tasks.derived.outcomes import (
    RECHECK,
    changed_rows,
    eligible_at,
    left_by,
    scope_of,
)
from algotrade_ingestion.tasks.derived.paths.close_fields import (
    FieldLoader,
    refuse_unstored,
    rule_licence,
)
from algotrade_ingestion.tasks.derived.paths.wanted import Wanted, positions_wanted
from algotrade_ingestion.tasks.framework.run import IngestRun, TaskContext
from algotrade_ingestion.tasks.maintenance.quality import Check

TASK = "share-outcomes"
SOURCE = "share_outcomes"
TABLE = SHARE_PATH
TABLES = (TABLE,)
NO_BAR = "NO_BAR"
CHUNK = 40  # window ends whose bars are read at once in a backfill
KEY = ("instrument_id", "position_key", "benchmark")  # a row's identity in a partition
NO_BENCHMARK = "none"
SHOWN = 5  # reasons listed per window in the run stats
SITE = FileConfigStore(config_dir())
COLUMNS = tuple(c.name for c in spec_for(TABLE).columns if c.name not in COMMON)


def compute_share_outcomes(
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
    wanted = positions_wanted(load_edges(configs), load_templates(configs), SHARES)
    gone, listed, first = scope_of(ctx.reader, ends[-1])
    fields = FieldLoader(ctx.reader)
    features = site_features(configs) if any(w.fields for w in wanted) else None
    deepest = max((w.hold for w in wanted), default=0)
    record: RunRecord | None = None
    for i in range(0, len(ends), CHUNK):
        chunk = ends[i : i + CHUNK]
        lo = max(sessions_ending(chunk[0], deepest + 1)[0], first)
        panel = session_bars(ctx.reader, lo, chunk[-1], columns=("close",)) if wanted else None
        stamps = bar_stamps(ctx.reader, lo, chunk[-1]) if wanted else {}
        for t in chunk:
            left = left_by(t, gone, listed)
            with IngestRun(ctx, TASK, t) as run:
                _one(run, t, wanted, first, panel, stamps, left, fields, features)
            record = run.record
    assert record is not None
    return record


def _one(
    run: IngestRun, end: date, wanted: Sequence[Wanted], first: date, panel: SessionBars | None,
    stamps: Mapping[date, datetime], left: Mapping[str, date], fields: FieldLoader,
    features: FeatureSet | None,
) -> None:  # fmt: skip
    parts: dict[date, list[pd.DataFrame]] = {}  # one partition per start session, written once
    eligible: dict[date, list[str]] = {}
    for w in wanted:
        item = f"{w.benchmark}:{w.key}"  # one position under one benchmark
        window = Window(tuple(sessions_ending(end, w.hold + 1)))
        if window.start < first or panel is None:
            run.record_item(item, "BEFORE_HISTORY")
            continue
        refusal = "; ".join(refuse_unstored(run.reader, w.fields, window.sessions[1:])[:SHOWN])
        if refusal:
            run.record_item(item, f"REFUSED: {refusal}")
            run.stats[item] = {"refused": refusal}
            continue
        if window.start not in eligible:
            eligible[window.start] = sorted(eligible_at(run.reader, window.start))
        names = eligible[window.start]
        licence = rule_licence(features, w.fields)
        ticker = w.benchmark or NO_BENCHMARK
        resolver = run.resolver(window.start)
        bench = resolver.id_for(ticker) if resolver.knows(ticker) else None
        rows = path_rows(w, window, names, panel, stamps, left, fields, licence, bench)
        parts.setdefault(window.start, []).append(rows.assign(benchmark=ticker))
        reasons = rows.loc[rows["outcome_status"] == UNMEASURED, "outcome_reason"]
        run.record_item(item, f"OK: {len(rows)} rows")
        run.stats[item] = {
            "position_key": w.key,
            "benchmark": ticker,
            "start": window.start.isoformat(),
            "rows": len(rows),
            "unmeasured": len(reasons),
            "unknown_closes": int(rows["exit_unknown_closes"].sum()),
            "reasons": {str(r): int(n) for r, n in reasons.value_counts().items()},
        }
    _publish(run, parts)


def path_rows(
    w: Wanted, window: Window, names: Sequence[str], panel: SessionBars,
    stamps: Mapping[date, datetime], left: Mapping[str, date], fields: FieldLoader, licence: str,
    benchmark: str | None = None,
) -> pd.DataFrame:  # fmt: skip
    """The ``share_path@v1`` rows of position ``w`` over ``window`` for ``names`` (the eligible
    names at S), ``knowledge_ts`` per row (NaT: known when written); ``benchmark``: the benchmark's
    instrument id (None: no benchmark, its return null). The ``benchmark`` column is the
    caller's."""
    close = wide_closes(panel.window(window.start, window.end), window, "close")
    bench = (
        close[benchmark]
        if benchmark is not None and benchmark in close.columns
        else pd.Series(math.nan, index=close.index)
    )
    after = window.sessions[1:]
    values, field_known = [], []
    for day in after:
        found, known = fields(day, w.fields, names)
        values.append(found)
        field_known.append(known)
    side = w.outcome.side
    rows = []
    for name in names:
        prices = close[name] if name in close.columns else pd.Series(math.nan, index=close.index)
        path = [
            ShareClose(d, float(prices[d]), values[i].get(name)) for i, d in enumerate(after)
        ]  # a missing close is NaN: the walker never prices across it
        gone = left.get(name)
        delisted = gone is not None and gone > window.start
        while delisted and path and not math.isfinite(path[-1].close):
            path.pop()  # a delisted name's path ends at its last bar (DELISTED there)
        walk = walk_share(
            side, window.start, float(prices[window.start]), path, w.rules, w.hold,
            delisted=delisted,
        )  # fmt: skip
        # the first missing close decides the reason: a flagged bar there, or a plain gap
        gap = next((d for d in window.sessions if not math.isfinite(float(prices[d]))), None)
        flagged = gap is not None and (name, gap) in panel.flagged
        row = _row(name, w, window, float(prices[window.start]), walk, stamps, field_known, flagged)
        moved = (
            float(bench[walk.exit_session]) / float(bench[window.start]) - 1.0
            if walk is not None
            else math.nan
        )
        rows.append({**row, "licence": licence, "benchmark_return": moved})
    return pd.DataFrame(rows, columns=[c for c in (*COLUMNS, "knowledge_ts") if c != "benchmark"])


def _row(
    name: str, w: Wanted, window: Window, entry: float, walk: ShareWalk | None,
    stamps: Mapping[date, datetime], field_known: Sequence[datetime | None], flagged: bool,
) -> dict[str, object]:  # fmt: skip
    """One row of ``name``: its walk to the exit, or UNMEASURED with its reason (no walk)."""
    base = {
        "instrument_id": name, "ts": close_time(window.start), "position_key": w.key,
        "window_end": window.end, "hold_sessions": w.hold,
        "entry_close": entry if math.isfinite(entry) and entry > 0 else math.nan,
    }  # fmt: skip
    if walk is None:
        return {
            **base, "exit_session": None, "exit_index": None, "exit_kind": None,
            "gross_return": math.nan, "underlying_return": math.nan, "max_adverse": math.nan,
            "exit_unknown_closes": 0, "outcome_status": UNMEASURED,
            "outcome_reason": BAD_BAR if flagged else NO_BAR, "knowledge_ts": pd.NaT,
        }  # fmt: skip
    delisted = walk.exit_kind == "DELISTED"
    read = [stamps.get(d) for d in window.sessions[: walk.exit_index + 1]]
    read += list(field_known[: walk.exit_index])
    known = [pd.Timestamp(s) for s in read if s is not None]
    return {
        **base, "exit_session": walk.exit_session, "exit_index": walk.exit_index,
        "exit_kind": walk.exit_kind, "gross_return": walk.gross_return,
        "underlying_return": walk.underlying_return,
        "max_adverse": math.nan if walk.max_adverse is None else walk.max_adverse,
        "exit_unknown_closes": walk.unknown_closes,
        "outcome_status": "DELISTED" if delisted else "COMPLETE", "outcome_reason": None,
        "knowledge_ts": pd.NaT if delisted or not known else max(known),
    }  # fmt: skip


def _publish(run: IngestRun, parts: Mapping[date, list[pd.DataFrame]]) -> None:
    """Write each start session's new or changed rows as one partition of ``share_path@v1``: the
    one publisher of the table. ``knowledge_ts`` comes from the rows (the write time where a row
    has none), never compared when finding what changed; a stored row whose values changed (a
    cleared flag, a late split or a restated bar the bars' own stamps do not show) is known no
    earlier than this write, so an earlier read never sees the correction."""
    now = pd.Timestamp(run.clock())
    for start, frames in sorted(parts.items()):
        both = pd.concat(frames, ignore_index=True)
        stored = run.reader.table(TABLE, start)
        fresh = changed_rows(stored, both, KEY).reset_index(drop=True)
        if fresh.empty:
            continue
        known = pd.to_datetime(fresh.pop("knowledge_ts"), utc=True).fillna(now)
        if stored is not None and not stored.empty:
            had = pd.MultiIndex.from_frame(stored[list(KEY)].astype(str))
            again = pd.MultiIndex.from_frame(fresh[list(KEY)].astype(str)).isin(had)
            known = known.where(~again | (known >= now), now)
        run.write(TABLE, fresh, SOURCE, session=start, known=known)


def check_share_outcomes(reader: StoreReader, session: date, s: SourcesSettings) -> list[Check]:
    """The acceptance of the ``share-outcomes`` step for window end ``session``: for each position
    window the run computed, every name in the universe at S with a bar at S (counted again here)
    has a stored row of that key and benchmark ending at ``session``; a position the run refused
    fails."""
    del s  # the step's acceptance needs no settings
    runs = [r for r in reader.runs(TASK, session) if r.status == RunStatus.COMPLETE]
    if not runs:
        return [Check("share_outcomes", "FAIL", f"no complete share-outcomes run for {session}")]
    problems: list[str] = []
    windows = unmeasured = 0
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
        eligible = len(eligible_at(reader, start))
        part = reader.table(TABLE, start)
        mine = 0
        if part is not None:
            ends = pd.to_datetime(part["window_end"]).dt.date == session
            ours = (part["position_key"] == value["position_key"]) & (
                part["benchmark"] == value["benchmark"]
            )
            mine = int((ends & ours).sum())
        if eligible != value["rows"] or mine != value["rows"]:
            problems.append(
                f"{key[:60]}: {eligible} eligible at {start}, {value['rows']} rows, {mine} stored"
            )
        unmeasured += int(value["unmeasured"])
    if problems:
        return [Check("share_outcomes", "FAIL", "; ".join(problems[:SHOWN]))]
    return [
        Check(
            "share_outcomes", "PASS",
            f"{windows} share position windows closed by {session}, every eligible name has a "
            f"row; {unmeasured} UNMEASURED (a gap or a flagged bar before the exit)",
        )
    ]  # fmt: skip
