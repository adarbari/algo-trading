"""A named sleeve over a range spanning the Cboe cutover runs as two slices (ADR 0088 decision 11):
the open run over Cboe rows and the owner-only history run, each its own run job; the open one is
all a trader's reads see."""

from datetime import date

import pytest

from algotrade.config.edges.document import job_name
from algotrade.config.edges.positions.chain import OPTION_HISTORY
from algotrade.config.edges.positions.templates import KIND, NAME
from algotrade.config.user import UserContext
from algotrade.data.chains import FIRST_CBOE_CHAIN_SESSION
from algotrade.services.jobs import JobStatus, LocalJobRunner
from algotrade.services.jobs.handlers import LIBRARY_HANDLERS
from algotrade.storage.backends.memory import MemoryBackend, MemoryRuns
from algotrade.storage.configs.files import MemoryConfigStore
from algotrade.storage.tables.result_writer import ResultWriter
from tests.unit.services.evaluation.time_series import test_sleeve as ts
from tests.unit.services.evaluation.time_series.conftest import AS_OF

USER = UserContext("site")
OPEN_FIRST, OPEN_LAST = date(2026, 10, 5), date(2026, 10, 16)


@pytest.fixture
def split_world(monkeypatch: pytest.MonkeyPatch):
    """Trades of every trial over January 2024 (history) and over 5-16 October 2026 (Cboe)."""
    edge = ts.sleeve_edge()
    backend = MemoryBackend()
    ts.world(edge, backend=backend)
    monkeypatch.setattr(ts, "FIRST", OPEN_FIRST)
    monkeypatch.setattr(ts, "LAST", OPEN_LAST)
    cboe = {"price_source": "cboe", "licence": "open"}
    days = [d for _, d in ts.entries(edge)]
    changes = {(v, d): cboe for v in ts.PNL for d in days}
    reader = ts.world(edge, backend=backend, changes=changes)
    return edge, reader, ResultWriter(backend)


def test_a_sleeve_across_the_cutover_publishes_an_open_run_and_a_history_run(split_world) -> None:
    _, reader, writer = split_world
    configs = MemoryConfigStore(
        {
            ("site", KIND, NAME): ts.SITE.load("site", KIND, NAME),
            ("site", "edges", "drift"): _document(),
        }
    )
    runner = LocalJobRunner(
        MemoryRuns(), LIBRARY_HANDLERS, {"reader": reader, "writer": writer, "configs": configs}
    )
    params = {
        "edge": "drift", "start": "2024-01-02",
        "end": OPEN_LAST.isoformat(), "as_of": AS_OF.isoformat(),
    }  # fmt: skip
    job = runner.wait(runner.submit("edge-eval", params, USER))
    assert job.status is JobStatus.COMPLETE, job.error
    assert [s["source"] for s in job.result["slices"]] == ["cboe", "option_history"]
    open_runs = writer.runs_for(job_name("drift", "site"))
    history_runs = writer.runs_for(job_name("drift", "site", OPTION_HISTORY))
    assert len(open_runs) == 1 and len(history_runs) == 1
    assert open_runs[0].stats["price_source"] == "cboe"
    assert history_runs[0].stats["price_source"] == OPTION_HISTORY
    assert open_runs[0].stats["evidence_licence"] == "open"
    assert history_runs[0].stats["evidence_licence"] == "personal"
    assert date.fromisoformat(open_runs[0].stats["range"][0]) >= FIRST_CBOE_CHAIN_SESSION
    assert date.fromisoformat(history_runs[0].stats["range"][1]) < FIRST_CBOE_CHAIN_SESSION
    runner.shutdown()


def _document() -> dict:
    from tests.unit.config.edges.test_document import document  # noqa: PLC0415
    from tests.unit.config.edges.test_named import SLEEVE  # noqa: PLC0415

    return document(**SLEEVE)
