"""``explain``: the admin-only chain behind a gap (ADR 0056), from stored facts only.

A construction site knows the leaf (a table with nothing for the session). ``explain`` walks
upstream of it: the table's own writer step in the session's latest nightly run record (which
records each step's ``tables`` since ADR 0056; an older record has none, so the chain stops at
the table), and, when that step is fine, the tables its feature group reads
(``FeatureGroup.inputs``, a bounded depth). A step that is not SUCCEEDED becomes a STEP link,
with a SOURCE link before it when it was SKIPPED because a source was down. Called only for
admins, through one dataloader per request: a trader's read never pays for it."""

from collections.abc import Mapping
from datetime import date
from typing import Any

from algotrade.core.model.fields import group_of_table
from algotrade.features.registry import GROUPS
from algotrade.services.read.availability.cause import (
    Cause,
    CauseLevel,
    CauseLink,
)
from algotrade.services.read.context import Stores
from algotrade.services.read.ops.runs import NIGHTLY

__all__ = ["explain"]

MAX_DEPTH = 3  # tables upstream of the leaf (a rollup over a rollup over a rollup)
PROBLEM = frozenset({"FAILED", "NOT_RUN", "SKIPPED", "WAITING"})  # a step that did not deliver
SKIPPED_PREFIX = "skipped: "

type Steps = Mapping[str, Mapping[str, Any]]


def _nightly(ctx: Stores, session: date) -> tuple[str | None, Steps]:
    """The run id and recorded steps of the session's latest nightly record (none: no record)."""
    found = ctx.reader.runs(NIGHTLY, session)
    if not found:
        return None, {}
    record = max(found, key=lambda r: r.started_at)
    steps = record.stats.get("steps")
    return record.run_id, steps if isinstance(steps, dict) else {}


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
    if status == "SKIPPED":
        source = words.removeprefix(SKIPPED_PREFIX)
        links.append(CauseLink(CauseLevel.SOURCE, name, "UNAVAILABLE", source, run_id, session))
    links.append(CauseLink(CauseLevel.STEP, name, status, words, run_id, session))
    return links


def _upstream(
    table: str, steps: Steps, run_id: str | None, session: date, depth: int
) -> list[CauseLink]:
    """The links upstream of ``table`` (root first); empty: nothing recorded explains it."""
    name = _writer(table, steps)
    if name is not None and steps[name].get("status") in PROBLEM:
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
    table = leaf.first(CauseLevel.TABLE)
    if table is None or table.session is None:
        return leaf
    run_id, steps = _nightly(ctx, table.session)
    upstream = _upstream(table.subject, steps, run_id, table.session, MAX_DEPTH)
    return Cause((*upstream, *leaf.links)) if upstream else leaf
