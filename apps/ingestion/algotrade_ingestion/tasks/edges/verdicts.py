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
- ``--expect-same-headlines`` (ADR 0088 design 2.6, risk 16: the deploy of a judge change): each
  canonical run's row under the CURRENT fingerprint (newly framed, or already stored) is compared,
  every ``EdgeSummary`` field, with the NEWEST row of the same (edge, judged run) under any other
  fingerprint, by ``knowledge_ts``. Any difference FAILS the run and nothing is written (the one
  publish is skipped); a run with no earlier row is counted ``no_prior``, never a failure. It
  works with ``--dry-run``, and must run before the next nightly (a new canonical run has no prior).
- The row is framed by the one framer the edge-eval publish uses
  (``services/evaluation/cross_section/detail/verdict.py``), from the run's committed rows through
  the reader's own judge call, so the stored headline is the live one.
- Every new row of the run is written in ONE publish (several partitions, one commit): all or none.
  A failure of one edge is counted (the run is PARTIAL) and never stops the others; under
  ``--expect-same-headlines`` it FAILS the run and skips the publish (it was not compared).
- Point in time: ``knowledge_ts`` is the run's clock at the write, never back-dated (a verdict
  under today's judge was not known when the run ended).
- Takes no lock of its own: it runs under the CLI's ingest lock, or the post-session workflow's
  second locked block (it saves a RUNNING record and publishes pending rows). Owner-run once after
  the table's release, then it is the post-session workflow's last step; never against a store an
  agent does not own.
"""

from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, fields
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
COUNTS = (
    "written", "would_write", "skipped", "none", "outside_window", "not_reached", "failed",
    "compared", "no_prior", "withheld",
)  # fmt: skip
SHOWN = 20  # mismatches and failures listed in the run's stats


@dataclass(frozen=True)
class Options:
    """What one run was asked: the window on a run's range end, ``limit`` (rows written at most),
    ``dry_run`` (count only), ``verify`` (a read-only check: judge the current
    rows too, list those that differ, write nothing) and ``expect_same`` (compare each new row
    with the newest earlier row of its run, fail and write nothing on any difference)."""

    start: date | None = None
    end: date | None = None
    limit: int | None = None
    dry_run: bool = False
    verify: bool = False
    expect_same: bool = False  # ``--expect-same-headlines``: fail, writing nothing, on any change


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
        self.changed: list[str] = []  # ``--expect-same-headlines``: a headline that moved
        self._stored: dict[date, dict[tuple[str, str, str], EdgeSummary]] = {}
        self._headlines: dict[date, dict[tuple[str, str], list[framer.Headline]]] = {}

    @property
    def blocked(self) -> bool:
        """``--expect-same-headlines`` found a moved headline, or could not compare an edge (its
        re-judge raised): nothing may publish, a deploy gate cannot pass on a partial comparison."""
        return bool(self.changed) or (self.opt.expect_same and bool(self.failed))

    def _note(self, key: str, status: str, count: str) -> None:
        self.run.record_item(key, status)
        self.counts[count] += 1

    def _have(self, day: date) -> dict[tuple[str, str, str], EdgeSummary]:
        if day not in self._stored:
            self._stored[day] = framer.stored_summaries(self.stores, day)
        return self._stored[day]

    def _earlier(self, day: date) -> dict[tuple[str, str], list[framer.Headline]]:
        if day not in self._headlines:
            self._headlines[day] = framer.stored_headlines(self.stores, day)
        return self._headlines[day]

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
        if current is not None and not (opt.verify or opt.expect_same):
            return self._note(edge.id, "CURRENT", "skipped")
        if current is None and opt.limit is not None and self.counts["written"] >= opt.limit:
            return self._note(edge.id, "NOT_REACHED", "not_reached")
        run_id = self.run.run_id
        frame = framer.rejudged_frame(self.stores, edge, found, run_id=run_id, now=self.clock())
        if frame is None:  # filtered above by the same test: a bug if it happens
            raise ConfigurationError(f"{edge.id}: the canonical run was not judged")
        if opt.expect_same:  # the row this edge has (or gets) under the current fingerprint
            now = current or next(iter(framer.summaries_of(frame).values()))
            self._compared(edge.id, found, wanted, now)
        if current is not None and not opt.verify:  # compared above, nothing to write
            return self._note(edge.id, "CURRENT", "skipped")
        if current is not None:  # --verify: the stored row against the live judge
            return self._verified(edge.id, current, frame)
        if opt.dry_run or opt.verify:  # a check never writes
            return self._note(edge.id, "DRY_RUN", "would_write")
        self._note(edge.id, "WRITTEN", "written")
        self.new.setdefault(day, []).append(frame)

    def _compared(self, key: str, found: runs.EdgeRun, wanted: str, now: EdgeSummary) -> None:
        """``--expect-same-headlines``: ``now`` (the headline under the current fingerprint)
        against the newest row of the same run under another fingerprint, field by field. No
        earlier row is counted, never a failure."""
        day = found.range_to
        assert day is not None  # a run in the window has a range end
        others = [
            h for h in self._earlier(day).get((key, found.run_id), []) if h.fingerprint != wanted
        ]
        if not others:
            self.counts["no_prior"] += 1
            return
        before = max(others, key=lambda h: h.knowledge_ts).summary
        self.counts["compared"] += 1
        moved = [
            f"{f.name}: {getattr(before, f.name)!r} -> {getattr(now, f.name)!r}"
            for f in fields(EdgeSummary)
            if getattr(before, f.name) != getattr(now, f.name)
        ]
        if moved:
            self.changed.append(f"{key}: {'; '.join(moved)}")

    def _verified(self, key: str, stored: EdgeSummary, frame: pd.DataFrame) -> None:
        live = next(iter(framer.summaries_of(frame).values()))
        if live == stored:
            return self._note(key, "CURRENT", "skipped")
        self.mismatches.append(f"{key}: stored {stored}, live {live}")
        self._note(key, "MISMATCH", "skipped")

    def publish(self) -> None:
        """Every new row, all partitions, in one commit (or none)."""
        if not self.new or self.opt.dry_run or self.opt.verify or self.blocked:
            return
        with self.run.writer.publishing(self.run.run_id, self.clock()):
            for day, frames in sorted(self.new.items()):
                self.run.writer.write_result(
                    framer.RESULT, day, self.run.run_id, pd.concat(frames, ignore_index=True),
                    pending=True,
                )  # fmt: skip

    def finish(self, edges_seen: int) -> None:
        run, opt = self.run, self.opt
        if self.blocked:  # nothing was written: the rows queued are withheld
            self.counts["withheld"] = self.counts["written"]
            self.counts["written"] = 0
        run.stats.update(self.counts)
        run.stats.update(
            edges=edges_seen,
            window=[opt.start and opt.start.isoformat(), opt.end and opt.end.isoformat()],
            limit=opt.limit,
            dry_run=opt.dry_run,
            verify=opt.verify,
            expect_same=opt.expect_same,
            changed=self.changed[:SHOWN],
            changed_count=len(self.changed),
            mismatches=self.mismatches[:SHOWN],
            mismatch_count=len(self.mismatches),
            failures=self.failed[:SHOWN],
        )
        if edges_seen and self.counts["failed"] == edges_seen:
            run.failed(f"every edge failed ({edges_seen}): {self.failed[0]}")
        if self.counts["not_reached"]:
            run.partial(f"{self.counts['not_reached']} edges left by --limit: run it again")
        if self.opt.expect_same and self.failed:
            run.failed(
                f"{len(self.failed)} edges could not be compared (nothing published): "
                f"{self.failed[0]}"
            )
        if self.changed:
            run.failed(
                f"{len(self.changed)} headlines differ from the earlier rows: {self.changed[0]}"
            )
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
