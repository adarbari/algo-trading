"""Every stored ``events/*`` table is either on the events timeline or declared not a timeline
event with a reason: a new table cannot join the Explore events page by its prefix (1,791 rows
for AAPL, 92% of them blank "Event" lines, owner decision 2026-10-22)."""

import tomllib

from algotrade.services.read.events.stored import EVENTS_PREFIX, NOT_TIMELINE, TIMELINE_KINDS
from tests.conftest import REPO_ROOT


def _stored_kinds() -> set[str]:
    tables = tomllib.loads((REPO_ROOT / "architecture" / "tables.toml").read_text())
    names = {str(t["name"]) for t in tables["table"]}
    return {n.removeprefix(EVENTS_PREFIX) for n in names if n.startswith(EVENTS_PREFIX)}


def test_every_events_table_is_on_the_timeline_or_declared_not() -> None:
    assert set(TIMELINE_KINDS) | set(NOT_TIMELINE) == _stored_kinds()


def test_no_kind_is_both_and_every_exclusion_has_a_reason() -> None:
    assert not set(TIMELINE_KINDS) & set(NOT_TIMELINE)
    assert all(reason.strip() for reason in NOT_TIMELINE.values())
