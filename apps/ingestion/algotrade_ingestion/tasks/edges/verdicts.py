"""``edge-verdicts``: store the headline of every site edge's canonical run in
``results/edge_verdict`` (ADR 0053 amendment 2026-10-22), so the edges list reads one small row
instead of judging each run's rows on every request.

One task is both the backfill (the first run: runs stored before the table) and the re-judge (every
later run: the judge's code, ``verdict.toml`` or an edge document changed, so the stored
fingerprints no longer match). It judges only each site edge's CURRENT canonical run, never a
user's edge, a hidden copy, an exploratory run or an older run (the list reads none of them).

- Resumable and idempotent by the store itself: an edge whose canonical run already has a row
  under the CURRENT fingerprint is skipped (a run cut short, or limited by ``--limit``, is finished
  by running it again); rows are keyed by (edge, judged run, fingerprint), so two runs write equal
  rows. A skipped row is only checked against the live judge with ``--verify``: a difference is
  listed as a mismatch in the run's stats, never overwritten.
- The row is framed by the one framer the edge-eval publish uses
  (``services/evaluation/cross_section/detail/verdict.py``), from the run's committed rows through
  the reader's own judge call, so the stored headline is the live one.
- Every new row of the run is written in ONE publish (several partitions, one commit): all or none.
  A failure of one edge is counted (the run is PARTIAL) and never stops the others.
- Point in time: ``knowledge_ts`` is the run's clock at the write, never back-dated (a verdict
  under today's judge was not known when the run ended).
- Takes no lock of its own: it runs under the CLI's ingest lock, or the post-session workflow's
  second locked block (it saves a RUNNING record and publishes pending rows). Owner-run once after
  the table's release, then it is the post-session workflow's last step; never against a store an
  agent does not own.
"""

from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime

import pandas as pd

from algotrade.config.user import SITE_USER, UserContext
from algotrade.core.model.errors import ConfigurationError
from algotrade.services.evaluation.cross_section.detail import verdict as framer
from algotrade.services.read.context import StoreContext, open_stores
from algotrade.services.read.evaluation import edges, runs
from algotrade.services.read.evaluation.edges import Edge
from algotrade.services.read.evaluation.verdict.model import EdgeSummary
from algotrade.storage.runs import RunRecord
from algotrade_ingestion.tasks.framework.run import IngestRun, TaskContext

TASK = "edge_verdicts"
COUNTS = ("written", "would_write", "skipped", "none", "outside_window", "not_reached", "failed")
SHOWN = 20  # mismatches and failures listed in the run's stats


@dataclass(frozen=True)
class Options:
    """What one run was asked: the window on a run's range end, ``limit`` (rows written at most),
    ``dry_run`` (count only) and ``verify`` (a read-only check: judge the current
    rows too, list those that differ, write nothing)."""

    start: date | None = None
    end: date | None = None
    limit: int | None = None
    dry_run: bool = False
    verify: bool = False


class _Pass:
    """One run's state: what each edge did, the rows to publish and what to report."""

    def __init__(
        self, run: IngestRun, stores: StoreContext, clock: Callable[[], datetime], opt: Options
    ) -> None:
        self.run, self.stores, self.opt = run, stores, opt
        self.clock = clock
        self.counts: Counter[str] = Counter(dict.fromkeys(COUNTS, 0))  # every count is in the stats
        self.mismatches: list[str] = []
        self.failed: list[str] = []
        self.new: dict[date, list[pd.DataFrame]] = {}
        self._stored: dict[date, dict[tuple[str, str, str], EdgeSummary]] = {}

    def _note(self, key: str, status: str, count: str) -> None:
        self.run.record_item(key, status)
        self.counts[count] += 1

    def _have(self, day: date) -> dict[tuple[str, str, str], EdgeSummary]:
        if day not in self._stored:
            self._stored[day] = framer.stored_summaries(self.stores, day)
        return self._stored[day]

    def edge(self, edge: Edge) -> None:
        """Judge one edge's canonical run (or note why not); a failure is counted, never raised."""
        try:
            self._edge(edge)
        except Exception as exc:  # one edge's failure never stops the others
            self.run.fail(edge.id, f"{type(exc).__name__}: {exc}", kind="FAILED")
            self.failed.append(f"{edge.id}: {type(exc).__name__}: {exc}")
            self.counts["failed"] += 1

    def _outside(self, edge: Edge, found: runs.EdgeRun | None) -> tuple[str, str] | None:
        """Why the run is not this pass's: (status, count), or None when it is."""
        if found is None or not framer.canonical_kind(edge, found):
            return "NONE", "none"  # the reader judges (or says no run) live
        day, opt = found.range_to, self.opt
        if day is None or not (opt.start or day) <= day <= (opt.end or day):
            return "OUTSIDE_WINDOW", "outside_window"
        return None

    def _edge(self, edge: Edge) -> None:
        found = runs.load_canonical_run(self.stores, edge).run
        if (why := self._outside(edge, found)) is not None or found is None:
            return self._note(edge.id, *(why or ("NONE", "none")))
        day, opt = found.range_to, self.opt
        wanted = framer.run_fingerprint(self.stores, edge, found)
        current = self._have(day).get((edge.id, found.run_id, wanted))
        if current is not None and not opt.verify:
            return self._note(edge.id, "CURRENT", "skipped")
        if current is None and opt.limit is not None and self.counts["written"] >= opt.limit:
            return self._note(edge.id, "NOT_REACHED", "not_reached")
        run_id = self.run.run_id
        frame = framer.rejudged_frame(self.stores, edge, found, run_id=run_id, now=self.clock())
        if frame is None:  # filtered above by the same test: a bug if it happens
            raise ConfigurationError(f"{edge.id}: the canonical run was not judged")
        if current is not None:  # --verify: the stored row against the live judge
            return self._verified(edge.id, current, frame)
        if opt.dry_run or opt.verify:  # a check never writes
            return self._note(edge.id, "DRY_RUN", "would_write")
        self._note(edge.id, "WRITTEN", "written")
        self.new.setdefault(day, []).append(frame)

    def _verified(self, key: str, stored: EdgeSummary, frame: pd.DataFrame) -> None:
        live = next(iter(framer.summaries_of(frame).values()))
        if live == stored:
            return self._note(key, "CURRENT", "skipped")
        self.mismatches.append(f"{key}: stored {stored}, live {live}")
        self._note(key, "MISMATCH", "skipped")

    def publish(self) -> None:
        """Every new row, all partitions, in one commit (or none)."""
        if not self.new or self.opt.dry_run or self.opt.verify:
            return
        with self.run.writer.publishing(self.run.run_id, self.clock()):
            for day, frames in sorted(self.new.items()):
                self.run.writer.write_result(
                    framer.RESULT, day, self.run.run_id, pd.concat(frames, ignore_index=True),
                    pending=True,
                )  # fmt: skip

    def finish(self, edges_seen: int) -> None:
        run, opt = self.run, self.opt
        run.stats.update(self.counts)
        run.stats.update(
            edges=edges_seen,
            window=[opt.start and opt.start.isoformat(), opt.end and opt.end.isoformat()],
            limit=opt.limit,
            dry_run=opt.dry_run,
            verify=opt.verify,
            mismatches=self.mismatches[:SHOWN],
            mismatch_count=len(self.mismatches),
            failures=self.failed[:SHOWN],
        )
        if edges_seen and self.counts["failed"] == edges_seen:
            run.failed(f"every edge failed ({edges_seen}): {self.failed[0]}")
        if self.counts["not_reached"]:
            run.partial(f"{self.counts['not_reached']} edges left by --limit: run it again")
        if self.mismatches:
            run.partial(f"{len(self.mismatches)} stored rows differ from the live judge")


def rejudge_edges(
    ctx: TaskContext, options: Options | None = None, edge_id: str | None = None
) -> RunRecord:
    """Judge the canonical run of every site edge (``edge_id``: that one) whose range end is in the
    window and that has no row under the current fingerprint, at most ``limit`` rows this run."""
    if ctx.configs is None:
        raise ConfigurationError("edge-verdicts needs the config store (the edge documents)")
    stores = open_stores(ctx.reader, ctx.configs, UserContext(SITE_USER))
    site = sorted((e for e in edges.load_edges(stores) if not e.mine), key=lambda e: e.id)
    if edge_id is not None:
        site = [e for e in site if e.id == edge_id]
        if not site:
            raise ConfigurationError(f"{edge_id!r} is not a site edge")
    now = ctx.clock()
    with IngestRun(ctx, TASK, now.date()) as run:
        work = _Pass(run, stores, ctx.clock, options or Options())
        for edge in site:
            work.edge(edge)
        work.publish()
        work.finish(len(site))
    return run.record
