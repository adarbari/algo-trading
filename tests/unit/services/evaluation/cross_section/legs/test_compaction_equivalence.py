"""ADR 0078 through the harness: compacting the outcome partitions changes no answer. The same
world (outcomes written by four nightly runs per start session: a first write, a value-identical
re-write, a revision of the two best names, a re-write of that) is stored twice in a real local
store, one copy compacted. At an ``as_of`` between the runs and at the latest, the edge's scores,
per-session stats, verdict and series rows are identical, and a second, incremental run after
compaction reuses every stored leg (ADR 0063: the partition sequence did not move and no stamp
is later), computing none."""

from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from algotrade.core.time.calendar import next_session
from algotrade.services.evaluation.cross_section.legs.reuse import INCREMENTAL
from algotrade.storage.backends.local import LocalBackend
from algotrade.storage.tables.schemas import FORWARD_RETURNS
from tests.helpers.stored_frames import stamped
from tests.unit.services.evaluation.cross_section.conftest import (
    DAYS,
    IDS,
    World,
    build_world,
    outcome_row,
)
from tests.unit.services.evaluation.cross_section.legs.test_reuse import run, same

KNOWNS = [datetime(2026, *md, 22, tzinfo=UTC) for md in ((9, 30), (10, 1), (10, 3), (10, 4))]
BETWEEN = datetime(2026, 10, 3, 12, tzinfo=UTC)  # after the re-write, before the revision
LATEST = datetime(2026, 10, 6, 12, tzinfo=UTC)


def runs_of(day: date) -> list[list[dict[str, Any]]]:
    first = [outcome_row(iid, i, day) for i, iid in enumerate(IDS)]
    revised = [outcome_row(iid, i, day, fwd_return=-0.2, fwd_excess_return=-0.2)
               for i, iid in enumerate(IDS) if i >= 18]  # fmt: skip
    after = [*first[:18], *revised]
    return [first, first, revised, after]


def store(root: Path) -> World:
    """The harness world on a local store with the outcomes' four runs per start session."""
    w = build_world(closed=[], backend=LocalBackend(root))
    for day in [*DAYS, next_session(DAYS[-1])]:
        for n, rows in enumerate(runs_of(day)):
            name = f"o{n}-{day}"
            w.writer.write_table(
                FORWARD_RETURNS, day, name, stamped(rows, day, name, KNOWNS[n], "outcomes"),
                pending=True,
            )  # fmt: skip
            w.backend.tables.commit_run(name, KNOWNS[n] + timedelta(minutes=10))
    return w


def compact(w: World) -> int:
    w.backend.tables.swap_grace_s = 0.0  # type: ignore[attr-defined]
    dropped = 0
    for day in w.backend.tables.dates(FORWARD_RETURNS):
        report = w.backend.tables.compact_runs(FORWARD_RETURNS, day)
        assert report.skipped is None, report
        dropped += report.runs_dropped
        w.backend.tables.sweep_orphans(FORWARD_RETURNS, day)
    return dropped


@pytest.fixture
def worlds(tmp_path: Path) -> tuple[World, World]:
    return store(tmp_path / "plain"), store(tmp_path / "packed")


@pytest.mark.parametrize("as_of", [BETWEEN, LATEST], ids=["between_runs", "latest"])
def test_the_edge_scores_are_the_same_after_compaction(
    worlds: tuple[World, World], as_of: datetime
) -> None:
    plain, packed = worlds
    assert compact(packed) > 0
    before, after = run(plain, as_of, write=False), run(packed, as_of, write=False)
    same(before, after)
    assert (before.trials, before.start_sessions) == (after.trials, after.start_sessions)
    assert before.results[0].measures[0].sessions > 0


def test_the_revision_is_visible_only_after_it_was_known(worlds: tuple[World, World]) -> None:
    """The control: the as_of values differ in answer, so the equalities above say something."""
    plain, packed = worlds
    compact(packed)
    for w in (plain, packed):
        mid, late = run(w, BETWEEN, write=False), run(w, LATEST, write=False)
        mid_rate, late_rate = (
            mid.results[0].measures[0].hit_rate,
            late.results[0].measures[0].hit_rate,
        )
        assert mid_rate is not None and late_rate is not None and mid_rate > late_rate


def test_an_incremental_run_after_compaction_reuses_every_leg(worlds: tuple[World, World]) -> None:
    packed = worlds[1]
    first = [run(w, LATEST, full=True) for w in worlds]
    assert compact(packed) > 0
    again = [run(w, LATEST) for w in worlds]
    for before, after in zip(first, again, strict=True):
        assert (after.mode, after.legs_computed) == (INCREMENTAL, 0)
        assert after.legs_reused == before.legs_computed > 0
        assert dict(after.legs_invalidated) == {}
        same(before, after)
    same(again[0], again[1])
