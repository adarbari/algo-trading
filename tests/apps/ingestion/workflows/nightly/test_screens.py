"""The nightly ``screens`` step: one ``screen`` job per screener; a COMPLETE run that went
without an optional source's table is a warning on the step, never its failure (ADR 0055)."""

from collections.abc import Mapping
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import pytest

from algotrade.config.site.nightly import Backfilling
from algotrade.config.site.settings import load_nightly
from algotrade.config.user import SITE_USER, UserContext
from algotrade.services.jobs import JobRecord, JobStatus
from algotrade.services.read.context import NotFoundError
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.configs.files import FileConfigStore, MemoryConfigStore
from algotrade.storage.locks import held
from algotrade_ingestion.workflows.nightly import screens as screens_module
from algotrade_ingestion.workflows.nightly.nightly import EDGE_SIGNALS, NIGHTLY, SNAPSHOT
from algotrade_ingestion.workflows.nightly.steps import StepResult, StepStatus
from algotrade_ingestion.workflows.post_session.post_session import EDGE_EVAL, POST_SESSION
from tests.conftest import REPO_ROOT

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


def test_only_snapshot_fetches_are_critical_and_latest_only() -> None:
    # 2026-10-16: the screens were latest-only, skipped in a catch-up session as "the source
    # serves the current snapshot", and the session was served complete without screener runs.
    # A critical step skipped as latest-only leaves its session complete: only a fetch of a
    # source that serves its current snapshot may be one (reads take the latest snapshot; a
    # session without its chains fails the screens' coverage).
    critical = {s.name: s.latest_only for s in NIGHTLY if s.critical and s.latest_only}
    assert critical == {"universe-build": SNAPSHOT, "chains": SNAPSHOT}


CHAINED = "rollups/instrument/option_liquidity@v1"


def _screens(*jobs: tuple[str, list[str]]) -> StepResult:
    summaries = [
        {"config": f"s{i}", "status": status, "missing_tables": missing}
        for i, (status, missing) in enumerate(jobs)
    ]
    return StepResult("screens", StepStatus.FAILED, result={"screens": summaries}, reason="x")


def test_chain_tables_are_the_rollups_computed_from_the_chains() -> None:
    chained = screens_module.chain_tables()
    assert {CHAINED, "rollups/instrument/iv30@v1"} <= chained  # iv_history via iv30 too
    assert "rollups/instrument/iv_history@v2" in chained
    assert "rollups/instrument/price_stats@v2" not in chained


def test_screens_short_only_for_want_of_never_fetched_chains_warn_and_hold_nothing() -> None:
    # Architect review 2026-10-16: a night the Mac slept through has no chains; failing its
    # screens would hold every later session back and lose their snapshot fetches.
    result = screens_module.without_chains(_screens(("complete", []), ("partial", [CHAINED])), True)
    assert result.status is StepStatus.SUCCEEDED and result.reason is None
    assert [(c["name"], c["status"]) for c in result.checks] == [("no_chains", "WARN")]
    assert result.checks[0]["detail"].startswith("s1 short of coverage")


@pytest.mark.parametrize(
    ("jobs", "unfetched"),
    [
        ((("partial", [CHAINED]), ("failed", [])), True),  # a failed job
        ((("partial", [CHAINED, "rollups/instrument/price_stats@v2"]),), True),  # not chains
        ((("partial", []),), True),  # short with every table present
        ((("partial", [CHAINED]),), False),  # the session's chains were fetched
    ],
)
def test_any_other_shortfall_still_fails_the_screens(
    jobs: tuple[tuple[str, list[str]], ...], unfetched: bool
) -> None:
    assert screens_module.without_chains(_screens(*jobs), unfetched).status is StepStatus.FAILED


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
            result={} if failed else {"signalled": {"drift": 5}, "mode": "full"},
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


def _audited(
    backend: MemoryBackend,
    edge: str,
    owner: str,
    day: date,
    mode: str = "audit",
    late: timedelta = timedelta(hours=2),
) -> None:
    """A completed ``edge-eval`` job of the edge for the post-session of ``day`` (submitted
    ``late`` after that day's midnight UTC) whose harness ran ``mode``."""
    submitted = datetime(day.year, day.month, day.day, tzinfo=UTC) + late
    params = {"edge": edge, "session": day.isoformat(), "mode": mode}
    job = JobRecord(f"j-{edge}-{day}", "edge-eval", params, owner, submitted, JobStatus.COMPLETE)
    job.result = {"mode": mode}
    backend.runs.save(job.to_run())


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


def test_edge_eval_summary_carries_the_mode_the_harness_ran_beside_the_requested_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A FULL fallback of an incremental request must show in the run record."""
    _edges(monkeypatch, ("drift", "site", "evidenced", True))
    backend = MemoryBackend()
    _audited(backend, "drift", "site", MONDAY)
    (summary,) = _eval_step(SignalJobs(), WEDNESDAY, backend).result["evaluations"]
    assert (summary["mode"], summary["effective_mode"]) == ("incremental", "full")


def test_the_nine_days_count_sessions_not_the_hour_the_audit_ran() -> None:
    """The audit of Monday 10-05 ran after midnight (on the 6th): measured from its session, the
    15th is 10 days on and due; measured from the day it started it would be 9 and wait."""
    backend = MemoryBackend()
    _audited(backend, "drift", "site", date(2026, 10, 5), late=timedelta(hours=26))
    assert screens_module.audit_due(backend, EDGE, date(2026, 10, 14)) is False
    assert screens_module.audit_due(backend, EDGE, date(2026, 10, 15)) is True


def test_a_missed_friday_audit_comes_on_the_next_run_over_nine_days_later() -> None:
    """Audited Friday 10-02; no post-session ran on Friday 10-09: Thursday 10-08 is incremental,
    Monday 10-12 (10 days on) is the audit, and Tuesday 10-13 is too while none is recorded."""
    backend = MemoryBackend()
    _audited(backend, "drift", "site", date(2026, 10, 2))
    assert screens_module.audit_due(backend, EDGE, date(2026, 10, 8)) is False
    assert screens_module.audit_due(backend, EDGE, date(2026, 10, 12)) is True
    assert screens_module.audit_due(backend, EDGE, date(2026, 10, 13)) is True


def test_an_audit_that_fell_back_to_full_or_is_another_edges_does_not_count() -> None:
    backend = MemoryBackend()
    _audited(backend, "drift", "site", WEDNESDAY - timedelta(days=1), mode="full")
    _audited(backend, "other", "site", WEDNESDAY - timedelta(days=1))
    assert screens_module.audit_due(backend, EDGE, WEDNESDAY) is True


FILING = "rollups/instrument/filing_text_similarity@v1"
LAUNCHES = "rollups/instrument/etf_launches@v1"
TODAY = date(2026, 10, 20)


def _window(**until: str) -> dict[str, Backfilling]:
    return {t: Backfilling(date.fromisoformat(u), "backfill") for t, u in until.items()}


def test_screens_short_only_of_a_declared_backfill_warn_and_stay_partial() -> None:
    # 2026-10-19: lazy_prices_similar, risk_factor_unchanged and etf_launch_recent were PARTIAL
    # on tables with no data yet (backfill in progress), which failed the critical screens step.
    window = _window(**{FILING: "2026-11-03", LAUNCHES: "2026-11-03"})
    result = screens_module.while_backfilling(
        _screens(("complete", []), ("partial", [FILING]), ("partial", [LAUNCHES, FILING])),
        window,
        TODAY,
    )
    assert result.status is StepStatus.SUCCEEDED and result.reason is None
    assert [(c["name"], c["status"]) for c in result.checks] == [("backfilling", "WARN")] * 2
    assert result.result["screens"][1]["status"] == "partial"  # the run stays PARTIAL


@pytest.mark.parametrize(
    ("jobs", "until"),
    [
        ((("partial", [FILING]), ("failed", [])), "2026-11-03"),  # a failed job
        ((("partial", [FILING, "rollups/instrument/price_stats@v2"]),), "2026-11-03"),  # other
        ((("partial", [FILING]),), "2026-10-19"),  # the entry lapsed
        ((("partial", [LAUNCHES]),), "2026-11-03"),  # a table not declared
        ((("partial", []),), "2026-11-03"),  # short with every table present
    ],
)
def test_any_other_shortfall_still_fails_while_a_backfill_is_declared(
    jobs: tuple[tuple[str, list[str]], ...], until: str
) -> None:
    window = _window(**{FILING: until})
    assert screens_module.while_backfilling(_screens(*jobs), window, TODAY).status is (
        StepStatus.FAILED
    )


def test_the_declared_backfills_excuse_the_stored_nightly_of_2026_10_19() -> None:
    """The nightly of 2026-10-19 failed its critical screens step: lazy_prices_similar and
    risk_factor_unchanged were PARTIAL on filing_text_similarity and short_squeeze_dtc on
    short_interest (its partition empty: the backfill stamped known_from 2026-10-20), and the
    last was not declared, so nothing was excused. Replayed over the site's own [backfilling]."""
    site = load_nightly(FileConfigStore(REPO_ROOT / "config", local=False)).backfilling
    short = "rollups/instrument/short_interest@v1"
    replay = _screens(("complete", []), ("partial", [FILING]), ("partial", [short]))
    result = screens_module.while_backfilling(replay, site, TODAY)
    assert result.status is StepStatus.SUCCEEDED
    # ... and a table nobody declared still fails it
    other = _screens(("partial", [short]), ("partial", ["rollups/instrument/price_stats@v2"]))
    assert screens_module.while_backfilling(other, site, TODAY).status is StepStatus.FAILED
    # ... as does the declared one once its entry lapsed
    assert screens_module.while_backfilling(replay, site, date(2026, 11, 4)).status is (
        StepStatus.FAILED
    )
