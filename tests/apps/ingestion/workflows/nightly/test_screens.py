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
from algotrade_ingestion.workflows.nightly.nightly import EDGE_EVAL, EDGE_SIGNALS, NIGHTLY
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


class SignalJobs:
    """One job per user, COMPLETE or FAILED as ``failing`` says."""

    def __init__(self, failing: tuple[str, ...] = ()) -> None:
        self.failing, self.asked = failing, []

    def run(self, kind: str, params: Mapping[str, Any], user: UserContext, force: bool) -> Any:
        self.asked.append((kind, user.user_id, dict(params), force))
        failed = user.user_id in self.failing
        return JobRecord(
            job_id=f"job-{user.user_id}",
            kind=kind,
            params=dict(params),
            user=user.user_id,
            submitted_at=datetime(2026, 10, 2, 22, tzinfo=UTC),
            status=JobStatus.FAILED if failed else JobStatus.COMPLETE,
            result={} if failed else {"signalled": {"drift": 5}},
            error="boom" if failed else None,
        )


def test_edge_signals_submit_one_job_per_record_owner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        screens_module,
        "paper_owners",
        lambda reader, store, session: [UserContext("alice"), UserContext("bob")],
    )
    jobs = SignalJobs()
    step = screens_module.signal_jobs(jobs, MemoryConfigStore({}), None)(D)  # type: ignore[arg-type]
    assert jobs.asked == [
        ("edge-signals", "alice", {"session": D.isoformat()}, True),
        ("edge-signals", "bob", {"session": D.isoformat()}, True),
    ]
    assert step.status is StepStatus.SUCCEEDED
    assert [s["user"] for s in step.result["signals"]] == ["alice", "bob"]


def test_a_failed_edge_signals_job_fails_the_step_naming_the_user(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        screens_module, "paper_owners", lambda reader, store, session: [UserContext("alice")]
    )
    step = screens_module.signal_jobs(SignalJobs(("alice",)), MemoryConfigStore({}), None)(D)  # type: ignore[arg-type]
    assert (
        step.status is StepStatus.FAILED
        and step.reason == "edge signals not complete: alice failed"
    )


def test_the_edge_signals_step_is_optional_and_waits_for_screens_only() -> None:
    step = next(s for s in NIGHTLY if s.name == EDGE_SIGNALS)
    assert not step.critical and step.needs == ("screens",) and step.latest_only


MONDAY, WEDNESDAY = date(2026, 10, 5), date(2026, 10, 7)  # the week's first session, a middle one
STORED = [date(2026, 8, 3), date(2026, 9, 30)]


def _edges(monkeypatch: pytest.MonkeyPatch, *edges: tuple[str, str, str, bool]) -> None:
    """Edges as (id, owner, status, has screeners) and stored outcomes from August."""
    docs = [
        SimpleNamespace(id=i, owner=o, status=st, screeners=("momo",) if has else (), baselines=())
        for i, o, st, has in edges
    ]
    monkeypatch.setattr(screens_module, "load_all_edges", lambda configs: docs)
    monkeypatch.setattr(screens_module, "stored_outcome_sessions", lambda reader: STORED)


def _eval_step(jobs: SignalJobs, session: date) -> Any:
    return screens_module.edge_eval_jobs(jobs, MemoryConfigStore({}), None)(session)  # type: ignore[arg-type]


def test_edge_eval_is_incremental_mid_week_and_audits_on_the_weeks_first_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _edges(monkeypatch, ("drift", "site", "evidenced", True), ("mine", "alice", "live", True))
    mid, first = SignalJobs(), SignalJobs()
    assert _eval_step(mid, WEDNESDAY).status is StepStatus.SUCCEEDED
    step = _eval_step(first, MONDAY)
    assert step.status is StepStatus.SUCCEEDED and step.result["mode"] == "audit"
    assert [(k, u, p["edge"], p["mode"], f) for k, u, p, f in mid.asked] == [
        ("edge-eval", "site", "drift", "incremental", True),
        ("edge-eval", "alice", "mine", "incremental", True),
    ]
    assert {p["mode"] for _, _, p, _ in first.asked} == {"audit"}
    params = mid.asked[0][2]
    assert (params["start"], params["end"], params["trigger"]) == (
        "2026-08-03", "2026-09-30", "nightly"
    )  # fmt: skip


def test_edge_eval_skips_closed_edges_and_edges_without_screeners(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _edges(
        monkeypatch,
        ("open", "site", "researching", True),
        ("done", "site", "rejected", True),
        ("stuck", "site", "blocked", True),
        ("empty", "site", "researching", False),
    )
    jobs = SignalJobs()
    _eval_step(jobs, WEDNESDAY)
    assert [p["edge"] for _, _, p, _ in jobs.asked] == ["open"]


def test_edge_eval_with_nothing_to_evaluate_is_skipped(monkeypatch: pytest.MonkeyPatch) -> None:
    _edges(monkeypatch, ("done", "site", "rejected", True))
    assert _eval_step(SignalJobs(), WEDNESDAY).status is StepStatus.SKIPPED


def test_a_failed_edge_eval_job_fails_the_step_without_holding_the_workflow(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _edges(monkeypatch, ("drift", "site", "evidenced", True), ("mine", "alice", "live", True))
    step = _eval_step(SignalJobs(("alice",)), MONDAY)
    assert step.status is StepStatus.FAILED
    assert step.reason == "edge evaluations not complete: alice/mine failed"
    assert [e["status"] for e in step.result["evaluations"]] == ["complete", "failed"]  # all ran
    declared = next(s for s in NIGHTLY if s.name == EDGE_EVAL)
    assert not declared.critical and declared.latest_only
    assert declared.needs == ("outcomes", "screens")
