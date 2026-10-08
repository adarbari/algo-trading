"""``explain``: the admin-only chain behind a gap (ADR 0056), from stored facts only.

A construction site knows the leaf (a table with nothing for the session). ``explain`` walks
upstream of it: the table's own writer step in the session's latest nightly run record (which
records each step's ``tables`` since ADR 0056; an older record has none, so the chain stops at
the table), and, when that step is fine, the tables its feature group reads
(``FeatureGroup.inputs``, a bounded depth). A step that is not SUCCEEDED becomes a STEP link,
with a SOURCE link before it when it was SKIPPED because a source was down. Called only for
admins, through one dataloader per request: a trader's read never pays for it."""

from collections.abc import Iterable, Mapping
from datetime import date
from typing import Any

from algotrade.core.model.fields import group_of_table
from algotrade.data import StoreReader
from algotrade.features.registry import GROUPS
from algotrade.services.read.availability.cause import (
    Cause,
    CauseLevel,
    CauseLink,
)
from algotrade.services.read.context import ResultCache, Stores
from algotrade.services.read.ops.runs import NIGHTLY

__all__ = ["explain", "failed_tables"]

MAX_DEPTH = 3  # tables upstream of the leaf (a rollup over a rollup over a rollup)
NOT_DELIVERED = frozenset({"FAILED", "NOT_RUN", "WAITING", "WAIVED"})
SKIPPED_PREFIX = "skipped: "

type Steps = Mapping[str, Mapping[str, Any]]


def not_delivered(step: Mapping[str, Any]) -> bool:
    """Whether a recorded step did not deliver its tables: FAILED, NOT_RUN, WAITING, WAIVED, or
    SKIPPED because a source was down (``skipped: ...``); a latest-only catch-up skip is not."""
    status = step.get("status")
    if status == "SKIPPED":
        return str(step.get("reason", "")).startswith(SKIPPED_PREFIX)
    return status in NOT_DELIVERED


def _nightly(
    reader: StoreReader, session: date, cache: ResultCache | None = None
) -> tuple[str | None, Steps]:
    """The run id and recorded steps of the session's latest nightly record (none: no record);
    read once per published state of the store when a ``cache`` is given."""
    key = ("nightly-steps", session, reader.visible_seq())
    hit = cache.get(key) if cache is not None else None
    if hit is not None:
        found: tuple[str | None, Steps] = hit
        return found
    runs = reader.runs(NIGHTLY, session)
    if not runs:
        result: tuple[str | None, Steps] = (None, {})
    else:
        record = max(runs, key=lambda r: r.started_at)
        steps = record.stats.get("steps")
        result = (record.run_id, steps if isinstance(steps, dict) else {})
    if cache is not None:
        cache.put(key, result)
    return result


def failed_tables(
    reader: StoreReader,
    session: date,
    missing: Iterable[str] = (),
    cache: ResultCache | None = None,
) -> frozenset[str]:
    """The tables a failure stands behind for ``session``: those of a nightly step that did not
    SUCCEED, the ``missing`` ones (no partition), and every feature group table that reads one
    (to ``MAX_DEPTH``). A gap in such a table is a system failure, never NOT_STORED."""
    _, steps = _nightly(reader, session, cache)
    bad = {
        str(t)
        for step in steps.values()
        if not_delivered(step)
        for t in step.get("tables", [])
        if isinstance(step.get("tables"), list)
    }
    bad |= set(missing)
    for _ in range(MAX_DEPTH):
        grown = {g.table for g in GROUPS.values() if any(i.table in bad for i in g.inputs)}
        if grown <= bad:
            break
        bad |= grown
    return frozenset(bad)


def _writer(table: str, steps: Steps) -> str | None:
    """The step whose recorded ``tables`` include ``table`` (none: unrecorded or no such step)."""
    for name, step in steps.items():
        recorded = step.get("tables")
        if isinstance(recorded, list) and table in recorded:
            return name
    return None


def _inputs(table: str) -> tuple[str, ...]:
    found = group_of_table(table)
    group = GROUPS.get(found[1]) if found is not None else None
    return tuple(i.table for i in group.inputs) if group is not None else ()


def _step_links(
    name: str, step: Mapping[str, Any], run_id: str | None, session: date
) -> list[CauseLink]:
    """The SOURCE (when it was skipped) and STEP links of a step that did not deliver."""
    status = str(step.get("status", ""))
    words = str(step.get("error") or step.get("reason") or status)
    links: list[CauseLink] = []
    if status == "SKIPPED" and words.startswith(
        SKIPPED_PREFIX
    ):  # a source down, not a catch-up skip
        source = words.removeprefix(SKIPPED_PREFIX)
        links.append(CauseLink(CauseLevel.SOURCE, name, "UNAVAILABLE", source, run_id, session))
    links.append(CauseLink(CauseLevel.STEP, name, status, words, run_id, session))
    return links


def _upstream(
    table: str, steps: Steps, run_id: str | None, session: date, depth: int
) -> list[CauseLink]:
    """The links upstream of ``table`` (root first); empty: nothing recorded explains it."""
    name = _writer(table, steps)
    if name is not None and not_delivered(steps[name]):
        return _step_links(name, steps[name], run_id, session)
    if depth <= 1:
        return []
    for source in _inputs(table):
        chain = _upstream(source, steps, run_id, session, depth - 1)
        if chain:
            message = f"{source} has no rows for {session.isoformat()}"
            return [*chain, CauseLink(CauseLevel.TABLE, source, "NO_ROW", message, run_id, session)]
    return []


def explain(ctx: Stores, leaf: Cause) -> Cause:
    """``leaf`` with the chain that explains it upstream, root cause first; ``leaf`` itself
    when it names no table or session, or nothing recorded explains it."""
    for table in (link for link in leaf.links if link.level is CauseLevel.TABLE):
        if table.session is None:
            continue
        run_id, steps = _nightly(ctx.reader, table.session, ctx.cache)
        upstream = _upstream(table.subject, steps, run_id, table.session, MAX_DEPTH)
        if upstream:
            return Cause((*upstream, *leaf.links))
    return leaf
