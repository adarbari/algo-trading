"""Nightly and IBKR: ``verify`` runs after the screens for the latest session only (optional);
``ibkr-contracts`` and ``ibkr-iv`` run after the chains and before the rollups (latest session
only); all are SKIPPED with a WARN (never FAILED) when ``[ibkr]`` is disabled or the gateway is
not reachable; the email gets a "Verification vs IBKR" section and IBKR IV coverage."""

from collections.abc import Mapping
from dataclasses import replace
from datetime import UTC, date, datetime
from typing import Any

import pytest

from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.runs import RunRecord
from algotrade.storage.tables.writers import StoreWriter
from algotrade_ingestion.tasks.framework import registry
from algotrade_ingestion.tasks.framework.run import IngestRun, TaskContext
from algotrade_ingestion.workflows.nightly import nightly as nightly_module
from algotrade_ingestion.workflows.nightly.nightly import FINALLY, NIGHTLY, SCREENS, run_nightly
from algotrade_ingestion.workflows.nightly.render import render_html, render_text
from algotrade_ingestion.workflows.nightly.report import build_report
from algotrade_ingestion.workflows.nightly.sessions import Plan
from algotrade_sources.vendors.ibkr.gateway import GatewayConfig, IbkrMarketData
from algotrade_sources.vendors.ibkr.market_data import IbkrSource
from tests.helpers.ingest_fakes import task_ctx
from tests.helpers.stored_frames import stamped, universe_rows

D, BEFORE = date(2026, 10, 2), date(2026, 10, 1)
IBKR_STEPS = ("verify", "ibkr-contracts", "ibkr-iv")


def _complete(name: str) -> Any:
    def run(ctx: TaskContext, params: Mapping[str, Any]) -> RunRecord:
        with IngestRun(ctx, f"fake-{name}", params["session"]) as r:
            r.stats["ran"] = name
        return r.record

    return run


@pytest.fixture
def others_fake(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every nightly task but the IBKR ones is a fake that completes; no acceptance checks."""
    monkeypatch.setattr(nightly_module, "NIGHTLY", tuple(replace(s, accept=()) for s in NIGHTLY))
    for step in (*NIGHTLY, *FINALLY):
        if step.name not in (SCREENS, *IBKR_STEPS):
            spec = registry.TASKS[step.name]
            fake = replace(spec, run=_complete(step.name), sources=(), skip=None)
            monkeypatch.setitem(registry.TASKS, step.name, fake)


def store() -> StoreWriter:
    writer = StoreWriter(MemoryBackend())
    writer.write_table("universe", D, "u", stamped(universe_rows(["AAPL"]), D, "u"))
    return writer


def test_verify_runs_after_screens_latest_only_and_optional() -> None:
    names = [s.name for s in NIGHTLY]
    assert names.index(SCREENS) < names.index("verify")
    verify = next(s for s in NIGHTLY if s.name == "verify")
    assert verify.latest_only and not verify.critical
    assert not any(s.critical for s in NIGHTLY if s.name.startswith("ibkr-"))


def test_ibkr_enrichment_runs_after_chains_before_rollups_latest_only() -> None:
    names = [s.name for s in NIGHTLY]
    chains, rollups = names.index("chains"), names.index("rollups")
    assert chains < names.index("ibkr-contracts") < names.index("ibkr-iv") < rollups
    assert all(s.latest_only for s in NIGHTLY if s.name.startswith("ibkr-"))


@pytest.mark.usefixtures("others_fake")
def test_disabled_ibkr_skips_verify_and_the_night_stays_complete() -> None:
    ctx = task_ctx(store())
    ctx = replace(ctx, unavailable={"ibkr": "[ibkr] is disabled in sources.toml"})
    summary = run_nightly(ctx, Plan([BEFORE, D]))
    for name in IBKR_STEPS:
        first, last = (r["steps"][name] for r in summary["runs"])
        assert first["status"] == "SKIPPED" and "latest closed session" in first["reason"]
        assert last == {
            "status": "SKIPPED",
            "critical": False,
            "duration_s": 0.0,
            "reason": "skipped: [ibkr] is disabled in sources.toml",
            "tables": list(
                registry.TASKS[name].tables
            ),  # recorded for the admin cause chain (ADR 0056)
        }
    assert summary["status"] == "SUCCEEDED"


@pytest.mark.usefixtures("others_fake")
@pytest.mark.allow_localhost
def test_an_unreachable_gateway_skips_verify_with_a_warn_and_a_hint() -> None:
    gateway = IbkrMarketData(GatewayConfig("127.0.0.1", 1, 1))  # nothing listens on port 1
    ctx = task_ctx(store(), sources={"ibkr": IbkrSource(gateway)})
    summary = run_nightly(ctx, Plan([D]))
    steps = summary["runs"][0]["steps"]
    assert summary["status"] == "SUCCEEDED"
    for name in IBKR_STEPS:
        assert steps[name]["status"] == "SKIPPED", name
        assert steps[name]["reason"].startswith("skipped: WARN: IB Gateway not reachable on 12")
    report = build_report(summary, {})
    [line] = report.verification
    assert line.status == "SKIPPED" and "not reachable" in line.note
    assert any("IB Gateway (Read-Only API" in h for h in report.hints)
    assert "VERIFICATION VS IBKR" in render_text(report)
    assert "Verification vs IBKR" in render_html(report)


def test_the_email_section_lists_counts_and_failing_examples() -> None:
    result = {
        "instruments": 21,
        "checks": {"PASS": 180, "WARN": 2, "FAIL": 1, "NA": 7},
        "failing": [
            {"symbol": "RPGL", "check": "close", "status": "FAIL", "ours": 12.5,
             "theirs": 12.0, "note": "rel diff; worst session 2026-09-24 of 260 compared"},
        ],
    }  # fmt: skip
    summary = {
        "status": "COMPLETE",
        "sessions": [D.isoformat()],
        "runs": [
            {"session": D.isoformat(), "steps": {"verify": {"status": "COMPLETE",
                                                             "duration_s": 400.0,
                                                             "result": result}}}
        ],
        "steps": {},
    }  # fmt: skip
    report = build_report(summary, {})
    text, html = render_text(report), render_html(report)
    assert "COMPLETE: 21 instruments; PASS 180, WARN 2, FAIL 1, NA 7" in text
    assert "RPGL close FAIL: ours 12.5 vs IBKR 12 (rel diff; worst session" in text
    assert "RPGL close FAIL" in html and "Verification vs IBKR" in html
    assert build_report(summary, {}) == report  # deterministic


def test_the_email_shows_ibkr_iv_coverage_backfill_and_pacing() -> None:
    result = {"underlyings": 4200, "with_contract": 4150, "with_iv": 3900, "coverage_pct": 92.9,
              "backfilled": 100, "backfill_pending": 3100, "backfill_eta_h": 17.2,
              "rows": 4000}  # fmt: skip
    summary = {
        "status": "COMPLETE",
        "sessions": [D.isoformat()],
        "runs": [{"session": D.isoformat(), "steps": {"ibkr-iv": {"status": "COMPLETE",
                                                                  "duration_s": 2100.0,
                                                                  "result": result}}}],
        "steps": {},
    }  # fmt: skip
    record = RunRecord("ibkr_iv-x", "ibkr_iv", D, datetime(2026, 10, 2, 22, tzinfo=UTC))
    record.stats = {"pacing": {"ibkr_historical": {"requests": 200, "limiter_wait_s": 1990.0},
                               "ibkr": {"requests": 8800, "limiter_wait_s": 170.0}}}  # fmt: skip
    report = build_report(summary, {(D.isoformat(), "ibkr-iv"): record})
    [line] = [s for s in report.steps if s.step == "ibkr-iv"]
    assert dict(line.counts) == {"underlyings": 4200, "with_iv": 3900, "coverage_pct": 92.9,
                                 "backfilled": 100, "backfill_pending": 3100,
                                 "backfill_eta_h": 17.2}  # fmt: skip
    text = render_text(report)
    assert "coverage_pct" in text and "ibkr_historical" in text
