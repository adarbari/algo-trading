"""The nightly ``screens`` step: one ``screen`` job per screener; a COMPLETE run that went
without an optional source's table is a warning on the step, never its failure (ADR 0055)."""

from collections.abc import Mapping
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import pytest

from algotrade.config.edges.document import job_name
from algotrade.config.user import SITE_USER, UserContext
from algotrade.services.jobs import JobRecord, JobStatus
from algotrade.services.read.context import NotFoundError
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.configs.files import MemoryConfigStore
from algotrade.storage.locks import held
from algotrade.storage.runs import RunRecord
from algotrade_ingestion.workflows.nightly import screens as screens_module
from algotrade_ingestion.workflows.nightly.nightly import EDGE_SIGNALS, NIGHTLY
from algotrade_ingestion.workflows.nightly.steps import StepStatus
from algotrade_ingestion.workflows.post_session.post_session import EDGE_EVAL, POST_SESSION

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


def test_an_edge_below_its_usual_range_is_one_warning_line_never_a_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owners = [UserContext("site"), UserContext("alice")]
    monkeypatch.setattr(screens_module, "paper_owners", lambda reader, store, session: owners)
    monkeypatch.setattr(screens_module, "open_context", lambda reader, c, user, day: user)
    live = {"site": [("drift", "4 of 20 closed trades won.")], "alice": []}
    monkeypatch.setattr(
        screens_module,
        "below_range",
        lambda user, cutoff: tuple(
            SimpleNamespace(edge_id=e, headline=h) for e, h in live[user.user_id]
        ),
    )
    step = screens_module.signal_jobs(SignalJobs(), MemoryConfigStore({}), object())(D)  # type: ignore[arg-type]
    assert step.status is StepStatus.SUCCEEDED
    assert step.result["below_range"] == [
        {"user": "site", "edge": "drift", "headline": "4 of 20 closed trades won."}
    ]
    assert step.checks == [
        {"name": "edge_below_range", "status": "WARN", "detail": "below the usual range: drift"}
    ]


def test_a_live_state_that_cannot_be_read_is_logged_and_a_warning_never_a_failure(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(
        screens_module, "paper_owners", lambda reader, store, session: [UserContext("site")]
    )

    def broken(reader: Any, configs: Any, user: Any, day: Any) -> Any:
        raise NotFoundError("nothing stored")

    monkeypatch.setattr(screens_module, "open_context", broken)
    with caplog.at_level("WARNING"):
        step = screens_module.signal_jobs(SignalJobs(), MemoryConfigStore({}), object())(D)  # type: ignore[arg-type]
    assert step.status is StepStatus.SUCCEEDED
    assert step.checks == [
        {
            "name": "edge_live_state",
            "status": "WARN",
            "detail": "live state of site not read: nothing stored",
        }
    ]
    assert "live state of site" in caplog.text


def test_no_edge_below_its_range_adds_no_line(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        screens_module, "paper_owners", lambda reader, store, session: [UserContext("site")]
    )
    monkeypatch.setattr(screens_module, "open_context", lambda reader, c, user, day: user)
    monkeypatch.setattr(screens_module, "below_range", lambda user, cutoff: ())
    step = screens_module.signal_jobs(SignalJobs(), MemoryConfigStore({}), object())(D)  # type: ignore[arg-type]
    assert step.checks == [] and "below_range" not in step.result


def test_the_edge_signals_step_is_optional_and_waits_for_screens_only() -> None:
    step = next(s for s in NIGHTLY if s.name == EDGE_SIGNALS)
    assert not step.critical and step.needs == ("screens",) and step.latest_only


MONDAY, TUESDAY, WEDNESDAY = date(2026, 10, 5), date(2026, 10, 6), date(2026, 10, 7)
STORED = [date(2026, 8, 3), date(2026, 9, 30)]


def _edges(monkeypatch: pytest.MonkeyPatch, *edges: tuple[str, str, str, bool]) -> None:
    """Edges as (id, owner, status, has screeners) and stored outcomes from August."""
    docs = [
        SimpleNamespace(id=i, owner=o, status=st, screeners=("momo",) if has else (), baselines=())
        for i, o, st, has in edges
    ]
    monkeypatch.setattr(screens_module, "load_all_edges", lambda configs: docs)
    monkeypatch.setattr(screens_module, "stored_outcome_sessions", lambda reader: STORED)


def _audited(backend: MemoryBackend, edge: str, owner: str, day: date, mode: str = "audit") -> None:
    """An evaluation run of the edge started on ``day`` in ``mode``."""
    start = datetime(day.year, day.month, day.day, 22, tzinfo=UTC)
    run = RunRecord("r-" + edge + day.isoformat(), job_name(edge, owner), STORED[-1], start)
    backend.runs.save(run.finish(start, stats={"mode": mode}))


def _eval_step(jobs: SignalJobs, session: date, backend: MemoryBackend | None = None) -> Any:
    step = screens_module.edge_eval_jobs(jobs, MemoryConfigStore({}), None, backend)  # type: ignore[arg-type]
    return step(session)


def test_edge_eval_audits_when_the_last_audit_is_old_else_is_incremental(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _edges(
        monkeypatch,
        ("drift", "site", "evidenced", True),
        ("mine", "alice", "live", True),
        ("fresh", "bob", "live", True),
    )
    backend = MemoryBackend()
    _audited(backend, "drift", "site", MONDAY)  # two days before Wednesday: incremental
    _audited(backend, "mine", "alice", WEDNESDAY - timedelta(days=10))  # over 9 days: audit
    jobs = SignalJobs()  # "fresh" has no audit on record: due
    assert _eval_step(jobs, WEDNESDAY, backend).status is StepStatus.SUCCEEDED
    assert [(k, u, p["edge"], p["mode"], f) for k, u, p, f in jobs.asked] == [
        ("edge-eval", "site", "drift", "incremental", True),
        ("edge-eval", "alice", "mine", "audit", True),
        ("edge-eval", "bob", "fresh", "audit", True),
    ]
    params = jobs.asked[0][2]
    assert (params["start"], params["end"], params["trigger"]) == (
        "2026-08-03", "2026-09-30", "nightly"
    )  # fmt: skip


EDGE = SimpleNamespace(id="drift", owner="site")


def test_the_audit_is_due_on_the_weeks_last_session_whatever_the_last_audit() -> None:
    backend = MemoryBackend()
    _audited(backend, "drift", "site", date(2026, 10, 8))  # yesterday
    assert screens_module.audit_due(backend, EDGE, date(2026, 10, 9)) is True  # a Friday
    assert screens_module.audit_due(backend, EDGE, date(2026, 10, 8)) is False  # a Thursday


def test_the_weeks_last_session_follows_the_exchange_calendar() -> None:
    """Good Friday 2026-04-03 is a holiday: the Thursday closes that week."""
    backend = MemoryBackend()
    _audited(backend, "drift", "site", date(2026, 4, 1))
    assert screens_module.audit_due(backend, EDGE, date(2026, 4, 2)) is True
    assert screens_module.audit_due(backend, EDGE, date(2026, 4, 1)) is False


def test_the_audit_is_due_only_over_nine_days_after_the_last_one() -> None:
    backend = MemoryBackend()
    _audited(backend, "drift", "site", WEDNESDAY - timedelta(days=9))
    assert screens_module.audit_due(backend, EDGE, WEDNESDAY) is False
    _audited(backend, "drift", "site", WEDNESDAY - timedelta(days=10), "incremental")
    assert screens_module.audit_due(backend, EDGE, WEDNESDAY) is False  # only audits count
    assert screens_module.audit_due(MemoryBackend(), EDGE, WEDNESDAY) is True  # none on record


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
    declared = next(s for s in POST_SESSION if s.name == EDGE_EVAL)
    assert not declared.critical  # the post-session workflow's step (ADR 0070)


def test_an_owner_with_an_evaluation_in_flight_is_a_busy_warning_not_a_crash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _edges(monkeypatch, ("drift", "site", "evidenced", True), ("mine", "alice", "live", True))
    backend, jobs = MemoryBackend(), SignalJobs()
    with held(backend.lock("edge-eval:alice")):  # another process is claiming alice's slot
        step = _eval_step(jobs, WEDNESDAY, backend)
    assert step.status is StepStatus.SUCCEEDED
    assert [p["edge"] for _, _, p, _ in jobs.asked] == ["drift"]  # alice's was not submitted
    assert [e["status"] for e in step.result["evaluations"]] == ["complete", "busy"]
    (warning,) = step.checks
    assert warning["name"] == "edge_eval_busy" and warning["detail"].startswith("mine:")
