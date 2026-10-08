"""Every open site edge document can be scored by the harness against what is stored (ADR 0053): its
measure and drawdown fields are outcome fields, its horizons and benchmark are ones the outcomes
task writes, the implied vol a ratio measure divides by is in the catalogue, and its schedule is
one the harness runs (an event schedule only while the edge has no screeners: ED4). And among
the services/evaluation modules only the harness reads outcomes, so the picks cannot see one."""

import ast
from datetime import date

import pytest

from algotrade.config.edges.document import ANNOUNCED_AHEAD, CLOSED, Edge
from algotrade.config.edges.loading import load_edges
from algotrade.core.model.errors import ConfigurationError
from algotrade.core.time.calendar import sessions_between
from algotrade.data.outcomes import OUTCOME_FIELDS
from algotrade.services.configs import field_catalog
from algotrade.services.evaluation.cross_section.hit import IMPLIED_VOL_FIELD, MEASURE_FIELDS
from algotrade.services.evaluation.cross_section.sessions import edge_sessions
from algotrade.storage.configs.files import FileConfigStore
from algotrade_ingestion.tasks.derived.outcomes import horizons_and_benchmarks
from tests.conftest import REPO_ROOT

STORE = FileConfigStore(REPO_ROOT / "config", local=False)
EDGES = [e for e in load_edges(STORE) if e.status not in CLOSED]  # a closed edge is not scored
HARNESS = "src/algotrade/services/evaluation/cross_section/harness.py"
PROTECTED = "algotrade.data.outcomes"


def _ids() -> list[str]:
    return [e.id for e in EDGES]


def _measure(edge: Edge) -> str:
    return edge.outcome.measure or "excess_return"


@pytest.mark.parametrize("edge", EDGES, ids=_ids())
def test_the_measure_and_the_path_condition_are_stored_outcome_fields(edge: Edge) -> None:
    fields = MEASURE_FIELDS[_measure(edge)]
    stored = [f for f in fields if f != IMPLIED_VOL_FIELD]
    assert set(stored) <= set(OUTCOME_FIELDS), f"{edge.id}: {fields} are not outcome fields"
    if edge.outcome.max_drawdown is not None:
        assert "fwd_max_drawdown" in OUTCOME_FIELDS


@pytest.mark.parametrize("edge", EDGES, ids=_ids())
def test_horizons_and_benchmark_are_written_by_the_outcomes_task(edge: Edge) -> None:
    horizons, benchmarks = horizons_and_benchmarks(STORE)
    assert set(edge.outcome.horizon_sessions) <= set(horizons), f"{edge.id}: {horizons}"
    if edge.outcome.benchmark != "none":
        assert edge.outcome.benchmark in benchmarks


def test_the_implied_vol_a_ratio_measure_divides_by_is_in_the_catalogue() -> None:
    field_catalog(STORE).check_field(IMPLIED_VOL_FIELD, "IMPLIED_VOL_FIELD")


@pytest.mark.parametrize("edge", EDGES, ids=_ids())
def test_the_schedule_is_one_the_harness_runs(edge: Edge) -> None:
    try:
        edge_sessions(edge.schedule, sessions_between(date(2026, 1, 2), date(2026, 3, 31)), 5)
    except ConfigurationError:
        assert edge.event_class is not None, f"{edge.id}: {edge.schedule} is not an event class"
        assert not edge.screeners and not edge.baselines, (
            f"{edge.id}: an event schedule with screeners needs ED4's sessions"
        )
    assert ANNOUNCED_AHEAD  # the offsets are ED4's: no site edge sets one the harness ignores
    if edge.event_class is None:
        assert edge.outcome.start_offset_sessions == 0


def test_only_the_harness_reads_outcomes_within_services_evaluation() -> None:
    offenders = []
    for path in sorted((REPO_ROOT / "src/algotrade/services/evaluation").rglob("*.py")):
        rel = path.relative_to(REPO_ROOT).as_posix()
        names = {
            n
            for node in ast.walk(ast.parse(path.read_text()))
            for n in (
                [a.name for a in node.names] if isinstance(node, ast.Import) else
                [node.module or ""] if isinstance(node, ast.ImportFrom) else []
            )
        }  # fmt: skip
        if rel != HARNESS and any(n == PROTECTED or n.startswith(f"{PROTECTED}.") for n in names):
            offenders.append(rel)
    assert not offenders, f"only {HARNESS} may read outcomes: {offenders}"


# Owner decision 2026-10-08 (ADR 0053 amendment): fixed, never rolling.
FROZEN_FROM = date(2026, 4, 1)


@pytest.mark.parametrize("edge", EDGES, ids=_ids())
def test_every_open_edge_names_the_decided_frozen_period(edge: Edge) -> None:
    """An open edge is judged in the one frozen period; moving it needs an ADR amendment."""
    assert edge.frozen_from == FROZEN_FROM, f"{edge.id}: frozen_from must be {FROZEN_FROM}"
