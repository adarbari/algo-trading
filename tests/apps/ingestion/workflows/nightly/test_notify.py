import subprocess
import sys
from typing import Any

import pytest

from algotrade.config.settings import NightlySettings
from algotrade_ingestion.workflows.nightly import notify


def test_default_notifier_is_quiet_in_tests_and_when_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    assert isinstance(notify.default_notifier(NightlySettings()), notify.NullNotifier)
    monkeypatch.delitem(sys.modules, "pytest")
    assert isinstance(notify.default_notifier(NightlySettings()), notify.MacNotifier)
    off = NightlySettings(notify_desktop=False)
    assert isinstance(notify.default_notifier(off), notify.NullNotifier)
    monkeypatch.setattr(sys, "platform", "linux")
    assert isinstance(notify.default_notifier(NightlySettings()), notify.NullNotifier)
    notify.NullNotifier().notify("t", "m")


def test_mac_notifier_runs_osascript_with_quoted_text(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []

    def run(args: list[str], **kwargs: Any) -> None:
        calls.append(args)

    monkeypatch.setattr(subprocess, "run", run)
    notify.MacNotifier().notify("nightly", 'bars "failed" \\ x')
    assert calls == [
        [
            "osascript",
            "-e",
            'display notification "bars \\"failed\\" \\\\ x" with title "nightly"',
        ]
    ]


def test_message_lists_steps_that_did_not_complete() -> None:
    summary = {
        "status": "FAILED",
        "sessions": [],
        "runs": [],
        "steps": {"purge-raw": {"status": "FAILED"}},
    }
    assert notify.message(summary) == "FAILED (no session): purge-raw failed"
