"""The nightly ``screens`` step: one ``screen`` job per screener; a COMPLETE run that went
without an optional source's table is a warning on the step, never its failure (ADR 0055)."""

from collections.abc import Mapping
from datetime import UTC, date, datetime
from types import SimpleNamespace
from typing import Any

import pytest

from algotrade.config.user import SITE_USER, UserContext
from algotrade.services.jobs import JobRecord, JobStatus
from algotrade.storage.configs.files import MemoryConfigStore
from algotrade_ingestion.workflows.nightly import screens as screens_module
from algotrade_ingestion.workflows.nightly.steps import StepStatus

D = date(2026, 10, 2)
IBKR = "rollups/instrument/ibkr_iv@v1"


class FakeJobs:
    """Returns one COMPLETE job per screener with the result given for its config."""

    def __init__(self, results: Mapping[str, dict[str, Any]]) -> None:
        self.results = results

    def run(self, kind: str, params: Mapping[str, Any], user: UserContext, force: bool) -> Any:
        return JobRecord(
            job_id=f"job-{params['config']}",
            kind=kind,
            params=dict(params),
            user=user.user_id,
            submitted_at=datetime(2026, 10, 2, 22, tzinfo=UTC),
            status=JobStatus.COMPLETE,
            result=self.results[params["config"]],
        )


def _nightly(*ids: str) -> Any:
    configs = [
        SimpleNamespace(config=SimpleNamespace(id=i), user=UserContext(SITE_USER)) for i in ids
    ]
    return lambda store: configs


def test_an_optional_table_missed_by_a_complete_screen_is_a_warning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(screens_module, "nightly_screeners", _nightly("vrp_scanner", "other"))
    jobs = FakeJobs(
        {
            "vrp_scanner": {"coverage": "COMPLETE", "missing_optional_tables": [IBKR]},
            "other": {"coverage": "COMPLETE", "missing_optional_tables": []},
        }
    )
    step = screens_module.screen_jobs(jobs, MemoryConfigStore({}), None)(D)  # type: ignore[arg-type]
    assert step.status is StepStatus.SUCCEEDED
    (warning,) = step.checks
    assert warning["status"] == "WARN" and warning["name"] == "optional_sources"
    assert warning["detail"] == f"vrp_scanner ran without {IBKR}"


def test_screens_without_optional_misses_carry_no_warning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(screens_module, "nightly_screeners", _nightly("other"))
    jobs = FakeJobs({"other": {"coverage": "COMPLETE"}})
    step = screens_module.screen_jobs(jobs, MemoryConfigStore({}), None)(D)  # type: ignore[arg-type]
    assert step.status is StepStatus.SUCCEEDED and step.checks == []
