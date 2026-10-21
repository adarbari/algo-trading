"""``run_edge_evals``: two edges on two worker processes give the stored result rows of the same
edges run one after the other (ADR 0059 amendment 2026-10-20). A real file store and config
directory, spawned workers, one process pool."""

from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pandas as pd
import tomlkit
from tests.unit.services.evaluation.cross_section.conftest import (
    ACTIVE,
    DAYS,
    build_world,
    edge_document,
    screen,
)

from algotrade.config.user import UserContext
from algotrade.data import StoreReader
from algotrade.services.jobs.api import run_job
from algotrade.services.jobs.edge_pool import (
    EdgeTask,
    PoolSettings,
    _evaluate,
    _fail_in_flight,
    run_edge_evals,
)
from algotrade.services.jobs.exclusive import EDGE_EVAL, claim_edge_eval
from algotrade.services.jobs.handlers import LIBRARY_HANDLERS
from algotrade.services.jobs.models import JobRecord, JobStatus
from algotrade.storage.backends.local import LocalBackend
from algotrade.storage.configs.files import FileConfigStore
from algotrade.storage.tables.result_writer import ResultWriter

AS_OF = datetime(2026, 10, 5, tzinfo=UTC)
EDGES = ("drift", "drift2")
RESULTS = "results/edge_eval"


def _configs(root: Path) -> Path:
    config = root / "config"
    files = {
        "site/presets/selections/active.toml": ACTIVE,
        "site/presets/screeners/momo/v1.toml": screen(),
        **{
            f"site/edges/{e}/edge.toml": edge_document(id=e, frozen_from=DAYS[2].isoformat())
            for e in EDGES
        },
    }
    for name, document in files.items():
        path = config / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(tomlkit.dumps(document))
    return config


def _params(edge: str) -> dict[str, Any]:
    return {
        "edge": edge, "start": DAYS[0].isoformat(), "end": DAYS[-1].isoformat(),
        "as_of": AS_OF.isoformat(), "trigger": "cli", "mode": "full",
    }  # fmt: skip


def _rows(root: Path) -> pd.DataFrame:
    reader = StoreReader(LocalBackend(root / "data"))
    frame = reader.table_range(RESULTS, date(2026, 1, 1), date(2027, 1, 1))
    assert frame is not None and not frame.empty
    frame = frame.drop(columns=["run_id", "knowledge_ts", "ts"], errors="ignore")
    return frame.astype(str).sort_values(list(frame.columns)).reset_index(drop=True)


def test_two_workers_give_the_rows_of_one_after_the_other(tmp_path: Path) -> None:
    for name in ("parallel", "serial"):
        build_world(backend=LocalBackend(tmp_path / name / "data"))
        _configs(tmp_path / name)
    par = tmp_path / "parallel"
    settings = PoolSettings(f"file://{par / 'data'}", str(par / "config"))
    backend = LocalBackend(par / "data")
    with claim_edge_eval(backend, "site"):  # the caller's claim, held for the whole run
        done = run_edge_evals(settings, [EdgeTask(e, "site", _params(e)) for e in EDGES], 2)
    assert [(d.edge, d.ok) for d in done] == [(e, True) for e in EDGES], [d.error for d in done]

    ser = tmp_path / "serial"
    sb = LocalBackend(ser / "data")
    resources = {
        "reader": StoreReader(sb), "writer": ResultWriter(sb),
        "configs": FileConfigStore(ser / "config"),
    }  # fmt: skip
    for e in EDGES:
        job = run_job(
            sb.runs, LIBRARY_HANDLERS, resources, EDGE_EVAL, _params(e), UserContext("site")
        )
        assert job.status.value != "FAILED", job.error
    pd.testing.assert_frame_equal(_rows(par), _rows(ser), check_exact=True)


def test_a_worker_that_cannot_open_the_store_is_a_failed_outcome_not_a_crash(
    tmp_path: Path,
) -> None:
    done = _evaluate(
        PoolSettings("bogus://x", str(tmp_path)), EdgeTask("drift", "site", _params("drift"))
    )
    assert not done.ok and "unsupported storage URL" in (done.error or "")


def test_the_unfinished_jobs_of_a_dead_pool_are_failed_for_its_own_edges_only(
    tmp_path: Path,
) -> None:
    backend = LocalBackend(tmp_path / "data")
    mine, other = _running(backend, "drift", "site"), _running(backend, "drift", "u1")
    _fail_in_flight(
        PoolSettings(f"file://{tmp_path / 'data'}", str(tmp_path)), [EdgeTask("drift", "site", {})]
    )
    states = {r.run_id: JobRecord.from_run(r).status for r in backend.runs.find(f"job:{EDGE_EVAL}")}
    assert states[mine] is JobStatus.FAILED and states[other] is JobStatus.RUNNING


def _running(backend: LocalBackend, edge: str, owner: str) -> str:
    record = JobRecord(
        f"j-{owner}", EDGE_EVAL, {"edge": edge}, owner, datetime.now(UTC), JobStatus.RUNNING
    )
    backend.runs.save(record.to_run())
    return record.job_id
