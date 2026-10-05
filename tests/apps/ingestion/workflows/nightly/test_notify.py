"""Notifications: the desktop alert, the summary email (fake SMTP; no network), the summary file."""

import json
import smtplib
import subprocess
import sys
from pathlib import Path
from typing import Any, ClassVar

import pytest

from algotrade.config.site.settings import NightlySettings
from algotrade_ingestion.workflows.nightly import notify
from algotrade_ingestion.workflows.nightly.notify import EmailConfig, EmailNotifier, Notice

ENV = {
    "ALGOTRADE_NOTIFY_EMAIL_TO": "owner@example.com, ops@example.com",
    "ALGOTRADE_SMTP_USER": "owner@example.com",
    "ALGOTRADE_SMTP_PASSWORD": "app-password-123",
}
NOTICE = Notice(
    "PARTIAL",
    notify.TITLE,
    "PARTIAL (2026-10-02): chains partial",
    subject="[algotrade] 2026-10-02 nightly: PARTIAL · 1 steps with failures",
    text="the text report\n",
    html="<!doctype html><p>the html report</p>",
)


class FakeSMTP:
    """Records what a ``smtplib.SMTP`` would do; ``fail_at`` raises at that call."""

    instances: ClassVar[list["FakeSMTP"]] = []

    def __init__(self, host: str, port: int, timeout: float = 0, **kwargs: Any) -> None:
        self.host, self.port, self.timeout, self.kwargs = host, port, timeout, kwargs
        self.calls: list[str] = []
        self.sent: list[Any] = []
        FakeSMTP.instances.append(self)

    def __enter__(self) -> "FakeSMTP":
        return self

    def __exit__(self, *exc: object) -> None:
        self.calls.append("quit")

    def starttls(self, context: Any = None) -> None:
        self.calls.append("starttls")

    def login(self, user: str, password: str) -> None:
        self.calls.append(f"login {user}")
        if password == "wrong":
            raise smtplib.SMTPAuthenticationError(535, b"Username and Password not accepted")

    def send_message(self, msg: Any) -> None:
        self.calls.append("send")
        self.sent.append(msg)


@pytest.fixture(autouse=True)
def _reset() -> None:
    FakeSMTP.instances = []


def config(port: int = 587, password: str = "app-password-123") -> EmailConfig:
    return EmailConfig(
        "smtp.test", port, "owner@example.com", ("owner@example.com",), "u", password
    )


def test_default_notifier_is_quiet_in_tests_and_when_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    assert isinstance(notify.default_notifier(NightlySettings()), notify.NullNotifier)
    monkeypatch.delitem(sys.modules, "pytest")
    assert isinstance(notify.default_notifier(NightlySettings()), notify.MacNotifier)
    off = NightlySettings(notify_desktop=False)
    assert isinstance(notify.default_notifier(off), notify.NullNotifier)
    both = notify.default_notifier(NightlySettings(email_enabled=True), ENV.get)
    assert isinstance(both, notify.Notifiers) and len(both.notifiers) == 2
    monkeypatch.setattr(sys, "platform", "linux")
    assert isinstance(notify.default_notifier(NightlySettings()), notify.NullNotifier)
    email_only = notify.default_notifier(NightlySettings(email_enabled=True), ENV.get)
    assert isinstance(email_only, EmailNotifier)
    disabled = NightlySettings(notify_enabled=False, email_enabled=True)
    assert isinstance(notify.default_notifier(disabled, ENV.get), notify.NullNotifier)
    assert notify.NullNotifier().notify(NOTICE) is None


def test_mac_notifier_alerts_only_when_not_complete(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []

    def run(args: list[str], **kwargs: Any) -> None:
        calls.append(args)

    monkeypatch.setattr(subprocess, "run", run)
    notify.MacNotifier().notify(Notice("PARTIAL", "nightly", 'bars "failed" \\ x'))
    notify.MacNotifier().notify(Notice("COMPLETE", "nightly", "all good"))
    assert calls == [
        [
            "osascript",
            "-e",
            'display notification "bars \\"failed\\" \\\\ x" with title "nightly"',
        ]
    ]


def test_message_lists_critical_steps_that_did_not_succeed() -> None:
    steps = {
        "bars": {"status": "FAILED", "critical": True},
        "rollups": {"status": "NOT_RUN", "critical": True},
        "shares": {"status": "FAILED", "critical": False},  # optional: a warning in the report
        "chains": {"status": "PARTIAL"},  # a record from before ADR 0039: counts as critical
    }
    summary = {
        "status": "FAILED",
        "sessions": ["2026-10-01"],
        "catch_up": {"held": ["2026-10-02"]},
        "runs": [{"session": "2026-10-01", "steps": steps}],
        "steps": {"purge-raw": {"status": "FAILED", "critical": False}},
    }
    assert notify.message(summary) == (
        "FAILED (2026-10-01): bars failed; chains partial; rollups not_run; held back: 2026-10-02"
    )
    assert notify.message({"status": "SUCCEEDED", "sessions": [], "runs": []}) == (
        "SUCCEEDED (no session)"
    )


def test_email_config_from_the_environment_only() -> None:
    settings = NightlySettings(smtp_host="smtp.gmail.com", smtp_port=587)
    got = notify.email_config(settings, ENV.get)
    assert isinstance(got, EmailConfig)
    assert got.recipients == ("owner@example.com", "ops@example.com")
    assert got.sender == "owner@example.com"  # FROM defaults to the first recipient
    assert (got.host, got.port, got.user) == ("smtp.gmail.com", 587, "owner@example.com")
    assert "app-password" not in repr(got)
    sender = {**ENV, "ALGOTRADE_NOTIFY_EMAIL_FROM": "bot@example.com"}
    assert notify.email_config(settings, sender.get).sender == "bot@example.com"  # type: ignore[union-attr]
    missing = notify.email_config(settings, {"ALGOTRADE_NOTIFY_EMAIL_TO": "a@b.c"}.get)
    assert missing == (
        "email not configured: set ALGOTRADE_SMTP_USER, ALGOTRADE_SMTP_PASSWORD (see .env.example)"
    )


def test_email_sends_text_and_html_over_starttls() -> None:
    notifier = EmailNotifier(config(), smtp=FakeSMTP)
    assert notifier.notify(NOTICE) is None
    (server,) = FakeSMTP.instances
    assert (server.host, server.port, server.timeout) == ("smtp.test", 587, notify.SMTP_TIMEOUT_S)
    assert server.calls == ["starttls", "login u", "send", "quit"]
    (msg,) = server.sent
    assert msg["Subject"] == NOTICE.subject and msg["To"] == "owner@example.com"
    assert msg.get_body(("plain",)).get_content() == "the text report\n"
    assert "the html report" in msg.get_body(("html",)).get_content()


def test_email_sends_complete_runs_too_and_port_465_uses_implicit_tls() -> None:
    notifier = EmailNotifier(config(port=465), smtp_ssl=FakeSMTP)
    complete = Notice("COMPLETE", notify.TITLE, "COMPLETE (2026-10-02)")
    assert notifier.notify(complete) is None
    (server,) = FakeSMTP.instances
    assert server.calls == ["login u", "send", "quit"] and "context" in server.kwargs
    assert server.sent[0]["Subject"] == "[algotrade] nightly: COMPLETE (2026-10-02)"


def test_email_problems_are_warnings_without_credentials() -> None:
    assert EmailNotifier("email not configured: set X").notify(NOTICE) == (
        "email not configured: set X"
    )
    warning = EmailNotifier(config(password="wrong"), smtp=FakeSMTP).notify(NOTICE)
    assert warning is not None and warning.startswith("email not sent (smtp.test:587): SMTP")
    assert "wrong" not in warning

    def refuse(*args: Any, **kwargs: Any) -> Any:
        raise ConnectionRefusedError("connection refused by app-password-123")

    warning = EmailNotifier(config(), smtp=refuse).notify(NOTICE)
    assert (
        warning
        == "email not sent (smtp.test:587): ConnectionRefusedError: connection refused by ***"
    )


def test_notifiers_join_warnings() -> None:
    both = notify.Notifiers([EmailNotifier("a"), notify.NullNotifier(), EmailNotifier("b")])
    assert both.notify(NOTICE) == "a; b"


def test_report_writes_the_file_and_records_delivery_warnings(tmp_path: Path) -> None:
    settings = NightlySettings(summary_path=str(tmp_path / "s.json"), email_enabled=True)
    summary = {"status": "COMPLETE", "sessions": [], "runs": [], "steps": {}, "warnings": []}
    out = notify.report(summary, settings, EmailNotifier(notify.email_config(settings, {}.get)))
    assert out["warnings"][0]["detail"].startswith("email not configured: set ALGOTRADE_NOTIFY")
    assert json.loads((tmp_path / "s.json").read_text())["warnings"] == out["warnings"]


def test_a_report_that_cannot_be_built_still_notifies(tmp_path: Path) -> None:
    class Broken:
        def runs(self, *args: Any) -> Any:
            raise OSError("store gone")

    settings = NightlySettings(summary_path=str(tmp_path / "s.json"))
    summary = {"status": "PARTIAL", "sessions": ["2026-10-02"], "steps": {},
               "runs": [{"session": "2026-10-02", "status": "PARTIAL", "steps": {}}]}  # fmt: skip
    seen: list[Notice] = []

    class Spy:
        def notify(self, notice: Notice) -> str | None:
            seen.append(notice)
            return None

    out = notify.report(summary, settings, Spy(), Broken())  # type: ignore[arg-type]
    assert seen[0].message == "PARTIAL (2026-10-02)" and seen[0].text == ""
    assert out["warnings"][0]["detail"] == "summary report not built: OSError: store gone"
