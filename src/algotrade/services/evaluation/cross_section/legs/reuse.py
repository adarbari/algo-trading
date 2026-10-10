"""Which stored legs a run reuses (ADR 0063 decisions 3 and 4): ``plan_reuse`` decides, for every
leg the run needs, whether the stored one still is what the run would compute, and so which decision
sessions the harness has to compute (all the legs of a session together: the reads log is one
row per session, so rewriting it rewrites or tombstones every leg of it).

A stored leg is reused only when all hold; the first that fails is its reason, counted in the
run record:

- the run is not FULL: not asked (``--full``), not an ``as_of`` before a stored leg's computation
  or outcome read (a historical run), not an edge whose report diagnostic needs the outcome rows
  (``earnings_expected``), and every horizon has a closed window;
- ``entry``: the leg has the entry session the run derives, and ``events``: the event names
  (an event schedule is read over the whole range on every run) are those it was measured on;
- ``inputs``: the session's reads log still matches the store: every partition it read exists
  and was committed no later than the log's ``inputs_seq``, a read that found nothing still finds
  nothing, a listing of partition dates up to D is the same, the earliest snapshot is still the
  earliest (``ReadRecord``);
- ``outcomes``: no outcome row of (S, horizon) became known after the leg's outcome read
  (``outcomes_as_of``, up to the run's ``as_of``) and the outcome partition is the commit the leg
  read (``outcome_seq``: a commit landing after its rows' ``knowledge_ts`` slips past a timestamp);
- ``draws``: a screener out of sample has its random draws.

A session with any leg not reused is computed in full; its legs that were fine are counted as
``session``. The closed windows of the run come from one columns-only read of the outcomes'
``knowledge_ts`` (``outcome_known``), the commit sequences from one ``partition_seq`` per table
over the range its reads span."""

from bisect import bisect_left, bisect_right
from collections import Counter
from collections.abc import Callable, Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import date, datetime
from typing import Any

from algotrade.core.model.errors import MissingDataError
from algotrade.data import ReadRecord, StoreReader, dates_digest
from algotrade.services.evaluation.cross_section.legs.rows import (
    DayReads,
    LegRecord,
    StoredLegs,
    encode_tombstone,
)
from algotrade.services.evaluation.cross_section.measures import SessionStat
from algotrade.services.evaluation.cross_section.random_picks import RandomStat

FULL = "full"
INCREMENTAL = "incremental"
Known = Mapping[tuple[date, int], datetime]  # (S, horizon) -> latest outcome knowledge_ts
LegId = tuple[str, str, str, int, date]  # (leg key, edge variant, screener, horizon, D)
Plan = tuple[tuple[str, int], str]  # ((edge variant, horizon), screener)


@dataclass(frozen=True)
class Need:
    """One leg the run needs if its window has closed: its id, its entry session S, whether its
    random draws are needed (a screener out of sample) and the event names at D (None: no event
    schedule), sorted."""

    leg: LegId
    entry: date
    drawing: bool
    events: tuple[str, ...] | None = None


@dataclass
class Reuse:
    """What ``plan`` decided. ``days``: the decision sessions to compute (None: all); ``closed``:
    the entry sessions with a closed window by horizon (empty for a FULL run: the harness reads
    them); ``reused``: the stored legs kept (draws dropped where the run does not need them) and
    ``reads`` their sessions' reads logs; ``invalidated``: stored legs recomputed, by reason."""

    mode: str
    days: frozenset[date] | None = None
    closed: dict[int, set[date]] = field(default_factory=dict)
    reused: dict[LegId, LegRecord] = field(default_factory=dict)
    reads: dict[date, DayReads] = field(default_factory=dict)
    invalidated: Counter[str] = field(default_factory=Counter)

    def snapshots(self) -> set[date]:
        """The universe snapshots the reused legs' screens read."""
        return {leg.snapshot for leg in self.reused.values() if leg.snapshot}

    def adopt(
        self,
        legs: dict[Plan, dict[date, SessionStat]],
        lost: dict[Plan, dict[date, str]],
        randoms: dict[Plan, dict[date, RandomStat]],
        plans: Collection[tuple[str, int]],
    ) -> None:
        """Add the reused legs of ``plans`` (edge variant, horizon) to what a run measured, by
        (plan, screener) and decision session, as it would have measured them."""
        for (_, edge_variant, variant, horizon, day), leg in self.reused.items():
            if (edge_variant, horizon) in plans:
                at = ((edge_variant, horizon), variant)
                legs.setdefault(at, {})[day] = leg.stat
                lost.setdefault(at, {})
                if leg.lost_table is not None:
                    lost[at][day] = leg.lost_table
                if leg.random is not None:
                    randoms.setdefault(at, {})[day] = leg.random


def plan_reuse(
    reader: StoreReader,
    stored: StoredLegs,
    needs: Sequence[Need],
    as_of: datetime,
    stamps: Callable[[Collection[date]], tuple[Known, Mapping[date, int]]],
    full: str | None = None,
) -> Reuse:
    """The run's reuse of ``stored`` over ``needs``; ``full``: why the run is FULL anyway (None:
    it is not, unless an ``as_of`` before a stored leg or a horizon without a closed window
    makes it so). ``stamps(entry sessions)``: the harness's read of the outcome partitions (it is
    the one reader of outcomes): per (S, horizon) the latest ``knowledge_ts`` by ``as_of``, and
    per S the partition's commit sequence."""
    if full is not None or not needs:
        return Reuse(FULL)
    keys = {n.leg[0] for n in needs}
    mine = {i: leg for i, leg in stored.legs.items() if i[0] in keys}
    if any(
        leg.known is None or max(leg.known, leg.outcomes_as_of) > as_of for leg in mine.values()
    ):
        return Reuse(FULL)  # a leg computed after ``as_of`` may hold rows not known then
    known, seqs = stamps({n.entry for n in needs})
    closed: dict[int, set[date]] = {n.leg[3]: set() for n in needs}
    for day, horizon in known:
        if horizon in closed:
            closed[horizon].add(day)
    if not all(closed.values()):
        return Reuse(FULL)  # nothing stored for a horizon: the harness raises, as a FULL run does
    wanted = [n for n in needs if n.entry in closed[n.leg[3]]]
    sound = _sound_days(reader, stored.reads, sorted({n.leg[4] for n in wanted}))
    reuse = Reuse(INCREMENTAL, closed=closed)
    todo: set[date] = set()
    reasons: dict[LegId, str | None] = {}
    for n in wanted:
        day = n.leg[4]
        found = mine.get(n.leg)
        reason = None if found is None else _stale(n, found, sound[day], known, seqs)
        reasons[n.leg] = reason
        if found is None or reason is not None:
            todo.add(day)
    for n in wanted:
        found, reason = mine.get(n.leg), reasons[n.leg]
        if n.leg[4] in todo:
            if found is not None:
                reuse.invalidated[reason or "session"] += 1
            continue
        assert found is not None
        reuse.reused[n.leg] = (
            found if n.drawing or found.random is None else replace(found, random=None)
        )
        reuse.reads[n.leg[4]] = stored.reads[n.leg[4]]
    reuse.days = frozenset(todo)
    return reuse


def _stale(
    need: Need,
    leg: LegRecord,
    sound: bool,
    known: Known,
    seqs: Mapping[date, int],
) -> str | None:
    """Why ``leg`` cannot stand in for ``need`` (None: it can)."""
    if leg.entry != need.entry:
        return "entry"
    if leg.event_ids != need.events:
        return "events"
    if not sound:
        return "inputs"
    if (
        known[need.entry, need.leg[3]] > leg.outcomes_as_of
        or seqs.get(need.entry) != leg.outcome_seq
    ):
        return "outcomes"
    if need.drawing and leg.random is None and not leg.stat.excluded_coverage:
        return "draws"
    return None


def _sound_days(
    reader: StoreReader, reads: Mapping[date, DayReads], days: Iterable[date]
) -> dict[date, bool]:
    """Per decision session whether its stored reads log still matches the store."""
    spans: dict[str, tuple[date, date]] = {}
    listed: set[str] = set()
    for day in days:
        for record in reads[day].reads if day in reads else ():
            if record.kind == "rows":
                low, high = spans.get(record.table, (record.start, record.end))
                spans[record.table] = (min(low, record.start), max(high, record.end))
            else:
                listed.add(record.table)
    stamps = {t: _Stamps(reader.partition_seq(t, lo, hi)) for t, (lo, hi) in spans.items()}
    listings = {t: reader.dates(t) for t in listed}
    return {day: day in reads and _unchanged(reads[day], day, stamps, listings) for day in days}


class _Stamps:
    """The committed partitions of a table over a range and their commit sequence, by date."""

    def __init__(self, found: Mapping[date, int]) -> None:
        self.days = sorted(found)
        self.seqs = [found[d] for d in self.days]

    def within(self, start: date, end: date) -> tuple[list[date], list[int]]:
        low, high = bisect_left(self.days, start), bisect_right(self.days, end)
        return self.days[low:high], self.seqs[low:high]


def _unchanged(
    reads: DayReads, day: date, stamps: Mapping[str, _Stamps], listings: Mapping[str, list[date]]
) -> bool:
    if reads.inputs_seq is None:
        return False
    for record in reads.reads:
        if record.kind == "rows":
            found, seqs = stamps[record.table].within(record.start, record.end)
            if any(s > reads.inputs_seq for s in seqs):
                return False  # re-committed, or a partition that was not there committed since
            if record.digest and dates_digest(found) != record.digest:
                return False  # a partition that was read is gone (purged)
        elif not _listing_unchanged(record, day, listings[record.table]):
            return False
    return True


def _listing_unchanged(record: ReadRecord, day: date, listing: Sequence[date]) -> bool:
    """A ``dates`` read: the earliest partition (``start == end``, one date) is still the
    earliest; any other listing, the dates up to D, is the same. A listing that went past D
    (``end > day``) was a read of the future and is never reusable."""
    if record.start == record.end and record.digest != dates_digest([]):
        return dates_digest(listing[:1]) == record.digest
    if record.end > day:
        return False
    return dates_digest([d for d in listing if d <= day]) == record.digest


def lost_error(lost: Mapping[date, str]) -> MissingDataError:
    """The error of a screener lost at every session, rebuilt from its stored legs: the table it
    had no data in at the first of them."""
    day = min(lost)
    hint = "run the ingestion that writes it"
    return MissingDataError(lost[day], f"no data for {day.isoformat()}", hint)


def tombstones(
    stored: StoredLegs,
    reuse: Reuse,
    computed: Iterable[Mapping[str, Any]],
    needs: Iterable[Need],
    rewritten: Collection[date],
    user_id: str,
    edge_id: str,
) -> list[dict[str, Any]]:
    """The rows that retire stored legs the run carries neither as reused nor as ``computed`` (leg
    rows): those of a trial the edge no longer has (a key none of ``needs`` has) and, at a
    session whose reads log the run rewrote (``rewritten``), any it did not compute again (the
    log would no longer say what that leg read)."""
    kept: set[LegId] = {*reuse.reused}
    for r in computed:
        kept.add(
            (
                r["leg_key"],
                r["edge_variant"],
                r["variant"],
                r["horizon_sessions"],
                r["session_date"],
            )
        )
    keys = {n.leg[0] for n in needs}
    return [
        encode_tombstone(leg, user_id, edge_id)
        for leg_id, leg in stored.legs.items()
        if leg_id not in kept and (leg_id[0] not in keys or leg_id[4] in rewritten)
    ]
