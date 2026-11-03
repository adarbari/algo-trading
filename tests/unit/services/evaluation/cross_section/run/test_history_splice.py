"""An option edge's history slice reads through the splice (ADR 0088 decision 11, F7): the chain
groups of the sessions before the cutover come from the option-history root, the trial that read
them is personal, a rerun reuses its legs (ADR 0063) and stays personal through their record, and a
partition restated in the root invalidates the session that read it. The fixture world's sessions
(September 2026) are before the cutover and its screen reads ``option_liquidity@v1``, one of the
nine groups; the root is a store built like the bought history's (``tests/helpers``)."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from algotrade.config.edges.positions.chain import OPTION_HISTORY
from algotrade.config.env import OPTION_HISTORY_URL
from algotrade.config.user import UserContext
from algotrade.core.model.errors import ConfigurationError
from algotrade.core.time.calendar import next_session
from algotrade.data import StoreReader
from algotrade.data.chains import FIRST_CBOE_CHAIN_SESSION
from algotrade.services.evaluation.cross_section.harness import evaluate_edge
from algotrade.services.evaluation.cross_section.legs.reuse import FULL, INCREMENTAL
from algotrade.services.evaluation.cross_section.results import write_edge_eval
from algotrade.services.evaluation.cross_section.run.evaluation import EdgeEvaluation
from algotrade.services.evaluation.cross_section.run.sources import SourceSlice
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.tables.writers import StoreWriter
from tests.helpers.stored_frames import stamped
from tests.unit.services.evaluation.cross_section.conftest import (
    DAYS,
    FEATURE,
    IDS,
    World,
    build_world,
    edge,
)

T1 = datetime(2026, 10, 6, 12, tzinfo=UTC)
SPLIT = {"frozen_from": DAYS[2].isoformat()}
EVERY = [*DAYS, next_session(DAYS[-1])]
HISTORY = SourceSlice(OPTION_HISTORY, DAYS[0], DAYS[-1])


def _rows(price: float = 100.0) -> list[dict[str, Any]]:
    return [{"instrument_id": iid, "underlying_price": price + 10 * i} for i, iid in enumerate(IDS)]


def _root() -> StoreWriter:
    """The history root with the chain group the screen reads, every session of the world."""
    root = StoreWriter(MemoryBackend())
    for day in EVERY:
        root.write_table(FEATURE, day, f"h-{day}", stamped(_rows(), day, f"h-{day}"))
    return root


def _run(w: World, root: StoreWriter | None, at: datetime, full: bool = False) -> EdgeEvaluation:
    """The history slice (``root``) or the plain run (None), its rows written."""
    spliced = {"job_source": OPTION_HISTORY, "history": StoreReader(root.backend)} if root else {}
    ev = evaluate_edge(
        w.reader, w.results, w.configs, UserContext("site"), edge(**SPLIT), DAYS[0], DAYS[-1], at,
        full=full, **spliced,
    )  # fmt: skip
    write_edge_eval(w.results, ev, at, source=HISTORY if root else None)
    return ev


def test_the_fixture_is_before_the_cutover() -> None:
    assert max(EVERY) < FIRST_CBOE_CHAIN_SESSION


def test_the_history_slice_reads_the_groups_from_the_root_and_its_trials_are_personal() -> None:
    """The same rows in the root as the plain world holds in its main store: the same statistics
    (the splice changes where a read goes, nothing else), every trial personal; the plain run over
    the main store's rows stays open (the open slice is unchanged)."""
    plain = _run(build_world(), None, T1, full=True)
    root = _root()
    history = _run(build_world(no_features=EVERY), root, T1, full=True)
    assert [r.stats for r in history.results] == [r.stats for r in plain.results]
    assert [r.measures for r in history.results] == [r.measures for r in plain.results]
    assert {r.licence for r in plain.results} == {"open"}
    assert {(r.licence, r.licences.evidence) for r in history.results if r.licences} == {
        ("personal", "personal")
    }


def test_a_rerun_reuses_the_spliced_legs_and_the_record_keeps_the_trial_personal() -> None:
    w, root = build_world(no_features=EVERY), _root()
    first = _run(w, root, T1, full=True)
    again = _run(w, root, T1)
    assert (first.mode, first.legs_reused) == (FULL, 0) and first.legs_computed > 0
    assert (again.mode, again.legs_computed, again.legs_reused) == (
        INCREMENTAL, 0, first.legs_computed,
    )  # fmt: skip
    assert [r.measures for r in again.results] == [r.measures for r in first.results]
    assert {r.licence for r in again.results} == {"personal"}  # read from the stamped records


def test_a_partition_restated_in_the_root_invalidates_the_session_that_read_it() -> None:
    w, root = build_world(no_features=EVERY), _root()
    _run(w, root, T1, full=True)
    day = DAYS[2]
    root.write_table(FEATURE, day, "restated", stamped(_rows(500.0), day, "restated"), pending=True)
    root.backend.tables.commit_run("restated", T1 + timedelta(minutes=30))
    again = _run(w, root, T1 + timedelta(hours=1))
    assert again.legs_computed > 0 and again.legs_invalidated.get("inputs", 0) > 0


def test_with_no_root_configured_the_history_slice_reads_as_before(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The history is not bought yet: an unset URL leaves the slice on the main store (no splice,
    so the nightly's option edges keep running), the trials as licensed as before."""
    monkeypatch.delenv(OPTION_HISTORY_URL, raising=False)
    plain = _run(build_world(), None, T1, full=True)
    w = build_world()
    unset = evaluate_edge(
        w.reader, w.results, w.configs, UserContext("site"), edge(**SPLIT), DAYS[0], DAYS[-1], T1,
        full=True, job_source=OPTION_HISTORY,
    )  # fmt: skip
    assert [r.measures for r in unset.results] == [r.measures for r in plain.results]
    assert {r.licence for r in unset.results} == {"open"}


def test_a_configured_root_that_is_not_mounted_fails_rather_than_reading_the_main_store(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv(OPTION_HISTORY_URL, (tmp_path / "unmounted").as_uri())
    w = build_world()
    with pytest.raises(ConfigurationError, match="mounted"):
        evaluate_edge(
            w.reader, w.results, w.configs, UserContext("site"), edge(), DAYS[0], DAYS[-1], T1,
            job_source=OPTION_HISTORY,
        )  # fmt: skip
