"""Nightly and the live verification: ``verify`` runs after the screens for the latest session
only, and is SKIPPED with a WARN (never FAILED) when ``[ibkr]`` is disabled or the gateway is
not reachable; the email gets a "Verification vs IBKR" section."""

from collections.abc import Mapping
from dataclasses import replace
from datetime import date
from typing import Any

import pytest

from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.runs import RunRecord
from algotrade.storage.tables.writers import StoreWriter
from algotrade_ingestion.sources.vendors.ibkr.gateway import GatewayConfig, IbkrMarketData
from algotrade_ingestion.sources.vendors.ibkr.market_data import IbkrSource
from algotrade_ingestion.tasks.framework import registry
from algotrade_ingestion.tasks.framework.run import IngestRun, TaskContext
from algotrade_ingestion.workflows.nightly.nightly import FINALLY, NIGHTLY, SCREENS, run_nightly
from algotrade_ingestion.workflows.nightly.render import render_html, render_text
from algotrade_ingestion.workflows.nightly.report import build_report
from algotrade_ingestion.workflows.nightly.sessions import Plan
from tests.helpers.ingest_fakes import task_ctx
from tests.helpers.stored_frames import stamped, universe_rows

D, BEFORE = date(2026, 10, 2), date(2026, 10, 1)


def _complete(name: str) -> Any:
    def run(ctx: TaskContext, params: Mapping[str, Any]) -> RunRecord:
        with IngestRun(ctx, f"fake-{name}", params["session"]) as r:
            r.stats["ran"] = name
        return r.record

    return run


@pytest.fixture
def others_fake(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every nightly task but ``verify`` is a fake that completes."""
    for step in (*NIGHTLY, *FINALLY):
        if step.name not in (SCREENS, "verify"):
            spec = registry.TASKS[step.name]
            fake = replace(spec, run=_complete(step.name), sources=(), skip=None)
            monkeypatch.setitem(registry.TASKS, step.name, fake)


def store() -> StoreWriter:
    writer = StoreWriter(MemoryBackend())
    writer.write_table("universe", D, "u", stamped(universe_rows(["AAPL"]), D, "u"))
    return writer


def test_verify_runs_after_screens_before_quality_latest_only() -> None:
    names = [s.name for s in NIGHTLY]
    assert names.index(SCREENS) < names.index("verify") < names.index("quality")
    assert next(s for s in NIGHTLY if s.name == "verify").latest_only


@pytest.mark.usefixtures("others_fake")
def test_disabled_ibkr_skips_verify_and_the_night_stays_complete() -> None:
    ctx = task_ctx(store())
    ctx = replace(ctx, unavailable={"ibkr": "[ibkr] is disabled in sources.toml"})
    summary = run_nightly(ctx, Plan([BEFORE, D]))
    first, last = (r["steps"]["verify"] for r in summary["runs"])
    assert first["status"] == "SKIPPED" and "latest closed session" in first["reason"]
    assert last == {
        "status": "SKIPPED",
        "duration_s": 0.0,
        "reason": "skipped: [ibkr] is disabled in sources.toml",
    }
    assert summary["status"] == "COMPLETE"


@pytest.mark.usefixtures("others_fake")
def test_an_unreachable_gateway_skips_verify_with_a_warn_and_a_hint() -> None:
    gateway = IbkrMarketData(GatewayConfig("127.0.0.1", 1, 1))  # nothing listens on port 1
    ctx = task_ctx(store(), sources={"ibkr": IbkrSource(gateway)})
    summary = run_nightly(ctx, Plan([D]))
    verify = summary["runs"][0]["steps"]["verify"]
    assert verify["status"] == "SKIPPED" and summary["status"] == "COMPLETE"
    assert verify["reason"].startswith("skipped: WARN: IB Gateway not reachable on 127.0.0.1:1")
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
