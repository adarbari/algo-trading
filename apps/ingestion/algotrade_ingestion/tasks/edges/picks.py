"""``edge-picks``: store what every site edge took at a session in ``results/edge_picks``
(ADR 0081), so the screener page's "counts toward" reads the edge's own picks instead of
ranking the run again.

One row per (edge, screener) per session, decided by the harness's own pick rule
(``services/evaluation/edge_picks/night.py``: ``screen_variant``, the edge's universe, its schedule
and ``top_k``); this task only chooses the sessions and edges, skips what is stored and publishes.

- Resumable and idempotent by the store itself: a (edge, screener) with a row for the session is
  not decided again (a run cut short is finished by running it again); a re-run writes the same
  rows. The nightly passes its session, ``--from/--to`` backfills a window of sessions.
- Every new row of a session is written in ONE publish with its siblings of the run (several
  partitions, one commit): all or none. A decision that cannot be made for missing data is a
  ``skipped`` ROW with its reason (a gap the page says, never a silent absence); an unexpected
  exception of one edge is a failed item (the run is PARTIAL) and never stops the others.
- Point in time: the decision reads what was known at the session; ``knowledge_ts`` is the write
  instant, never back-dated.
- Takes no lock of its own: it runs under the CLI's ingest lock or the nightly's.
"""

from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from time import monotonic

from algotrade.config.edges.document import Edge
from algotrade.config.edges.loading import load_edges
from algotrade.config.site.settings import SourcesSettings
from algotrade.config.user import SITE_USER, UserContext
from algotrade.core.model.errors import ConfigurationError
from algotrade.core.time.calendar import sessions_between
from algotrade.data import StoreReader
from algotrade.services.evaluation.edge_picks.frame import RESULT, edge_picks_frame
from algotrade.services.evaluation.edge_picks.night import SKIPPED, EdgePicks, Night, edge_night
from algotrade.storage.runs import RunRecord, RunStatus
from algotrade.storage.tables.edge_schemas import EDGE_PICKS
from algotrade_ingestion.tasks.framework.run import IngestRun, TaskContext
from algotrade_ingestion.tasks.maintenance.quality import Check

TASK = "edge_picks"
TABLE = EDGE_PICKS.name
TABLES = (TABLE,)
SHOWN = 20  # failures listed in the run's stats


@dataclass(frozen=True)
class Options:
    """What one run was asked: sessions ``start..end`` (default: the one session), one ``edge``."""

    start: date | None = None
    end: date | None = None
    edge: str | None = None


def stored_keys(reader: StoreReader, session: date) -> set[tuple[str, str]]:
    """The (edge, screener) pairs with a row stored for ``session``."""
    part = reader.table(TABLE, session)
    if part is None or part.empty:
        return set()
    site = part[part["user_id"] == SITE_USER]
    return set(zip(site["edge_id"], site["screener"], strict=True))


def _missing(edge_id: str, have: set[tuple[str, str]]) -> Callable[[str], bool]:
    """Whether a screener of ``edge_id`` has no row stored yet."""
    return lambda screener: (edge_id, screener) not in have


def _one_session(
    run: IngestRun, night: Night, edges: list[Edge], have: set[tuple[str, str]], failed: list[str]
) -> list[EdgePicks]:
    rows: list[EdgePicks] = []
    for edge in edges:
        try:
            rows += edge_night(night, edge, _missing(edge.id, have))
        except Exception as exc:  # one edge's failure never stops the others
            key = f"{edge.id}@{night.session.isoformat()}"
            run.fail(key, f"{type(exc).__name__}: {exc}", kind="FAILED")
            failed.append(f"{key}: {type(exc).__name__}: {exc}")
    return rows


def store_picks(ctx: TaskContext, session: date, options: Options | None = None) -> RunRecord:
    """Decide and publish the picks of every site edge not yet stored, for ``session`` (or the
    window ``options`` names)."""
    opt = options or Options()
    if ctx.configs is None:
        raise ConfigurationError("edge-picks needs the config store (the edge documents)")
    user = UserContext(SITE_USER)
    edges = sorted(
        (e for e in load_edges(ctx.configs, SITE_USER) if e.screeners), key=lambda e: e.id
    )
    if opt.edge is not None:
        edges = [e for e in edges if e.id == opt.edge]
        if not edges:
            raise ConfigurationError(f"{opt.edge!r} is not a site edge with a screener")
    days = sessions_between(opt.start or session, opt.end or session)
    written: dict[date, list[EdgePicks]] = {}
    failed: list[str] = []
    began = monotonic()
    with IngestRun(ctx, TASK, opt.end or session) as run:
        for day in days:
            night = Night(ctx.reader, ctx.configs, user, day)
            rows = _one_session(run, night, edges, stored_keys(ctx.reader, day), failed)
            if rows:
                written[day] = rows
            run.record_item(day.isoformat(), "WRITTEN" if rows else "CURRENT")
        now = ctx.clock()
        with run.writer.publishing(run.run_id, now):
            for day, rows in sorted(written.items()):
                frame = edge_picks_frame(rows, day, run.run_id, now)
                run.writer.write_result(RESULT, day, run.run_id, frame, pending=True)
        every = [r for rows in written.values() for r in rows]
        gaps = [f"{r.edge_id}/{r.screener}: {r.reason}" for r in every if r.status == SKIPPED]
        run.stats.update(
            edges=len(edges),
            pairs=sum(len(e.screeners) for e in edges),
            sessions=[d.isoformat() for d in days],
            written=len(every),
            by_status=dict(Counter(r.status for r in every)),
            skipped=gaps[:SHOWN],
            failures=failed[:SHOWN],
            seconds=round(monotonic() - began, 1),
        )  # fmt: skip
        if edges and failed and len(failed) >= len(edges) * len(days):
            run.failed(f"every edge failed: {failed[0]}")
    return run.record


def check_edge_picks(reader: StoreReader, session: date, s: SourcesSettings) -> list[Check]:
    """The acceptance of the ``edge-picks`` step for ``session``: a complete run exists and every
    site edge with a screener has a row for each screener it lists (a ``skipped`` row is a stated
    gap, listed in the message, never a missing one)."""
    runs = [r for r in reader.runs(TASK, session) if r.status == RunStatus.COMPLETE]
    if not runs:
        return [Check("edge_picks", "FAIL", f"no complete edge-picks run for {session}")]
    stored = stored_keys(reader, session)
    pairs = int(runs[-1].stats.get("pairs", 0))
    part = reader.table(TABLE, session)
    skipped = 0 if part is None else int((part["status"] == SKIPPED).sum())
    if len(stored) < pairs:
        return [
            Check(
                "edge_picks",
                "FAIL",
                f"{len(stored)} of {pairs} (edge, screener) rows stored for {session}",
            )
        ]
    return [
        Check(
            "edge_picks", "PASS" if not skipped else "WARN",
            f"{len(stored)} (edge, screener) rows stored for {session}; {skipped} skipped for data",
        )
    ]  # fmt: skip
