"""The golden cross-section reproduces the harness's known result: a positive 12-1 momentum decile
spread, identical on two runs (ADR 0053; the baseline of ``make evaluate`` holds the numbers)."""

from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from algotrade.config.env import config_dir
from algotrade.config.user import UserContext
from algotrade.core.time.clock import business_days
from algotrade.data import StoreReader
from algotrade.services.datasets import EDGE_FIXTURE_TAG
from algotrade.services.jobs import JobStatus, run_job
from algotrade.services.jobs.handlers import LIBRARY_HANDLERS
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.factory import open_config_store
from algotrade.storage.tables.result_writer import ResultWriter
from algotrade.storage.tables.writers import StoreWriter
from algotrade_ingestion.tasks.derived.outcomes import compute_outcomes
from algotrade_ingestion.tasks.derived.rollups import compute_rollups
from algotrade_ingestion.tasks.maintenance.golden import load_golden
from algotrade_sources.fixtures.catalog import CROSS_SECTION_BARS, CROSS_SECTION_TAG, START
from algotrade_sources.framework.base import FixtureSource
from tests.helpers.ingest_fakes import task_ctx

FROM, TO = date(2020, 1, 1), date(2021, 8, 10)
ONLY = ("price_stats@v2", "trend_stats@v2", "fundamentals@v3")


@pytest.fixture(scope="module")
def edge_store(golden_source: FixtureSource) -> MemoryBackend:
    """The golden store with the real rollups and outcomes tasks run over the golden range."""
    backend = MemoryBackend()
    ctx = task_ctx(StoreWriter(backend))
    load_golden(ctx, golden_source)
    compute_rollups(ctx, TO, FROM, TO, ONLY)
    compute_outcomes(ctx, TO, FROM, TO)
    return backend


def _evaluate(backend: MemoryBackend) -> dict[str, object]:
    resources = {
        "reader": StoreReader(backend),
        "writer": ResultWriter(backend),
        "configs": open_config_store(config_dir(None)),
    }
    params = {
        "edge": "momentum_12_1", "start": FROM.isoformat(), "end": TO.isoformat(),
        "as_of": datetime.now(UTC).isoformat(), "iv_field": None, "split_from": None,
    }  # fmt: skip
    job = run_job(backend.runs, LIBRARY_HANDLERS, resources, "edge-eval", params, UserContext("t"))
    assert job.status is JobStatus.COMPLETE, job.error
    return dict(job.result)


def test_golden_momentum_spread_is_positive_and_identical_on_two_runs(
    edge_store: MemoryBackend,
) -> None:
    first, second = _evaluate(edge_store), _evaluate(edge_store)
    whole = next(r for r in first["rows"] if r["slice_kind"] == "all")  # type: ignore[attr-defined]
    assert whole["decile_spread"] > 0
    assert whole["decile_sessions"] >= 5

    def measures(result: dict[str, object]) -> list[tuple[object, ...]]:
        return [
            (r["slice_kind"], r["slice_value"], r["decile_spread"], r["hit_rate"], r["picks"])
            for r in result["rows"]  # type: ignore[attr-defined]
        ]

    assert measures(first) == measures(second)


def test_the_size_baseline_is_scored_on_the_golden_store(edge_store: MemoryBackend) -> None:
    """The cross-section declares share counts, so ``feature.market_cap`` exists and the
    ``size_small`` baseline of the edge ranks names (a missing market cap never passes)."""
    rows = _evaluate(edge_store)["rows"]
    size = [r for r in rows if r["variant"] == "size_small" and r["slice_kind"] == "all"]  # type: ignore[attr-defined]
    assert size and size[0]["picks"] > 0


def test_the_makefile_range_is_the_catalogue_range() -> None:
    last = business_days(START, CROSS_SECTION_BARS)[-1].astype("datetime64[D]").astype(date)
    makefile = (Path(__file__).resolve().parents[2] / "Makefile").read_text()
    assert f"GOLDEN_FROM = {START}" in makefile
    assert f"GOLDEN_TO = {last.isoformat()}" in makefile
    assert f"{FROM}, {TO}" == f"{START}, {last}"


def test_the_strategy_grid_skips_the_catalogue_tag() -> None:
    assert EDGE_FIXTURE_TAG == CROSS_SECTION_TAG
