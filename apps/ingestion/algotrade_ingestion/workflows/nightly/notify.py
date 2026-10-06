"""After a nightly run: write its summary file, then notify (desktop alert + summary email).

``Notifier`` is the one interface: ``notify(notice)`` delivers a ``Notice`` and returns a
warning when it could not (it never raises). ``MacNotifier`` shows a macOS notification
(``osascript``; never under pytest) when the status is not SUCCEEDED or WAITING;
``EmailNotifier`` mails the full report (statistics + failure deep dive, ``report.py`` /
``render.py``) after every run over SMTP (STARTTLS; port 465: implicit TLS).
``config/site/nightly.toml`` ``[notify]`` turns notifications off or moves the summary
file (``var/logs/nightly-latest.json``);
``[notify.email]`` enables the email. Addresses and credentials come only from the
environment (``config/env.py``); a missing one, or an SMTP error, becomes a WARN in the run
summary and never fails the nightly. Credentials are never logged. A WAITING run (a source has
not published the session yet; ADR 0043) writes its summary file only: no desktop alert and no
email, because the next hourly run resumes it and the run that ends it (SUCCEEDED, or FAILED
at the deadline) sends the report.
"""

import json
import smtplib
import ssl
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from email.message import EmailMessage
from pathlib import Path
from typing import Any, Protocol

from algotrade.config import env
from algotrade.config.site.settings import NightlySettings
from algotrade.data import StoreReader
from algotrade_ingestion.workflows.nightly.records import load_report
from algotrade_ingestion.workflows.nightly.render import render_html, render_text

TITLE = "algotrade nightly"
SMTP_TIMEOUT_S = 30
IMPLICIT_TLS_PORT = 465
type Env = Callable[[str], str | None]


@dataclass(frozen=True)
class Notice:
    """What a nightly run tells its notifiers: one line, and the full report when built."""

    status: str  # SUCCEEDED / WAITING / FAILED
    title: str
    message: str  # one line: status, sessions, steps that did not complete
    subject: str = ""
    text: str = ""
    html: str = ""

    @property
    def alert(self) -> bool:
        return self.status not in ("SUCCEEDED", "WAITING", "COMPLETE")  # COMPLETE: before 0039


class Notifier(Protocol):
    def notify(self, notice: Notice) -> str | None:
        """Deliver ``notice``; -> a warning when it was not delivered. Never raises."""
        ...


class NullNotifier:
    def notify(self, notice: Notice) -> str | None:
        return None


class MacNotifier:
    """A macOS notification (``display notification``) for runs that did not succeed;
    failures are ignored."""

    def notify(self, notice: Notice) -> str | None:
        if not notice.alert:
            return None
        script = f"display notification {_quote(notice.message)} with title {_quote(notice.title)}"
        subprocess.run(["osascript", "-e", script], check=False, timeout=10, capture_output=True)
        return None


def _quote(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


@dataclass(frozen=True)
class EmailConfig:
    host: str
    port: int
    sender: str
    recipients: tuple[str, ...]
    user: str
    password: str = field(repr=False)


def email_config(settings: NightlySettings, lookup: Env = env.credential) -> EmailConfig | str:
    """The SMTP settings + addresses from the environment, or which variables are missing."""
    recipients = tuple(
        a.strip() for a in (lookup(env.NOTIFY_EMAIL_TO) or "").split(",") if a.strip()
    )
    user, password = lookup(env.SMTP_USER), lookup(env.SMTP_PASSWORD)
    missing = [
        name
        for name, value in (
            (env.NOTIFY_EMAIL_TO, recipients),
            (env.SMTP_USER, user),
            (env.SMTP_PASSWORD, password),
        )
        if not value
    ]
    if missing or user is None or password is None:
        return f"email not configured: set {', '.join(missing)} (see .env.example)"
    sender = lookup(env.NOTIFY_EMAIL_FROM) or recipients[0]
    return EmailConfig(settings.smtp_host, settings.smtp_port, sender, recipients, user, password)


class EmailNotifier:
    """Mails every run's report. ``config`` is an ``EmailConfig`` or why there is none."""

    def __init__(
        self,
        config: EmailConfig | str,
        smtp: Callable[..., smtplib.SMTP] | None = None,
        smtp_ssl: Callable[..., smtplib.SMTP] | None = None,
    ) -> None:
        self.config = config
        self._smtp = smtp
        self._smtp_ssl = smtp_ssl

    def message(self, notice: Notice) -> EmailMessage:
        assert isinstance(self.config, EmailConfig)
        msg = EmailMessage()
        msg["Subject"] = notice.subject or f"[algotrade] nightly: {notice.message}"
        msg["From"] = self.config.sender
        msg["To"] = ", ".join(self.config.recipients)
        msg.set_content(notice.text or notice.message + "\n")
        if notice.html:
            msg.add_alternative(notice.html, subtype="html")
        return msg

    def notify(self, notice: Notice) -> str | None:
        config = self.config
        if not isinstance(config, EmailConfig):
            return config
        try:
            self._send(config, self.message(notice))
        except Exception as exc:  # never fail the nightly for its email
            text = f"{type(exc).__name__}: {exc}".replace(config.password, "***")
            return f"email not sent ({config.host}:{config.port}): {text}"
        return None

    def _send(self, config: EmailConfig, msg: EmailMessage) -> None:
        context = ssl.create_default_context()
        if config.port == IMPLICIT_TLS_PORT:
            connect = self._smtp_ssl or smtplib.SMTP_SSL
            server = connect(config.host, config.port, timeout=SMTP_TIMEOUT_S, context=context)
        else:
            server = (self._smtp or smtplib.SMTP)(config.host, config.port, timeout=SMTP_TIMEOUT_S)
        with server:
            if config.port != IMPLICIT_TLS_PORT:
                server.starttls(context=context)
            server.login(config.user, config.password)
            server.send_message(msg)


class Notifiers:
    """Several notifiers; their warnings joined."""

    def __init__(self, notifiers: Sequence[Notifier]) -> None:
        self.notifiers = tuple(notifiers)

    def notify(self, notice: Notice) -> str | None:
        warnings = [w for n in self.notifiers if (w := n.notify(notice))]
        return "; ".join(warnings) or None


def default_notifier(settings: NightlySettings, lookup: Env = env.credential) -> Notifier:
    """The desktop notifier on macOS (outside tests) and the email when enabled; else a no-op."""
    if not settings.notify_enabled:
        return NullNotifier()
    chosen: list[Notifier] = []
    if settings.notify_desktop and sys.platform == "darwin" and "pytest" not in sys.modules:
        chosen.append(MacNotifier())
    if settings.email_enabled:
        chosen.append(EmailNotifier(email_config(settings, lookup)))
    if not chosen:
        return NullNotifier()
    return chosen[0] if len(chosen) == 1 else Notifiers(chosen)


BAD = ("FAILED", "NOT_RUN", "WAITING", "BLOCKED", "PARTIAL")  # BLOCKED / PARTIAL: before 0039


def message(summary: Mapping[str, Any]) -> str:
    """One line: status, sessions, the critical steps that did not succeed (optional ones
    are warnings in the report), and the sessions held back behind a failed one."""
    steps = [(name, step) for run in summary.get("runs", []) for name, step in run["steps"].items()]
    bad = sorted(
        {
            f"{name} {step['status'].lower()}"
            for name, step in steps
            if step["status"] in BAD and step.get("critical", True)
        }
    )
    sessions = ", ".join(summary.get("sessions", [])) or "no session"
    held = (summary.get("catch_up") or {}).get("held", [])
    tail = f"; held back: {', '.join(held)}" if held else ""
    return f"{summary['status']} ({sessions})" + (f": {'; '.join(bad)}" if bad else "") + tail


def notice(
    summary: Mapping[str, Any], reader: StoreReader | None, settings: NightlySettings
) -> tuple[Notice, str | None]:
    """The notice for a run: the full report when ``reader`` is given (-> a warning if the
    report could not be built; the one-line notice still goes out)."""
    base = Notice(str(summary["status"]), TITLE, message(summary))
    if reader is None:
        return base, None
    try:
        limit = settings.max_duration_minutes * 60
        built = load_report(reader, summary, settings.email_max_examples, limit)
    except Exception as exc:  # the report is a summary; never fail the nightly for it
        return base, f"summary report not built: {type(exc).__name__}: {exc}"
    return replace(
        base, subject=built.subject(), text=render_text(built), html=render_html(built)
    ), None


def _write(path: Path, summary: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary, indent=2, default=str))


def report(
    summary: Mapping[str, Any],
    settings: NightlySettings,
    notifier: Notifier,
    reader: StoreReader | None = None,
) -> dict[str, Any]:
    """Write the summary file, then notify (when enabled). Delivery problems become WARN
    entries in ``warnings`` (the file is rewritten with them). -> the summary."""
    out = dict(summary)
    path = Path(settings.summary_path)
    _write(path, out)
    if not settings.notify_enabled or out["status"] == "WAITING":
        return out
    note, problem = notice(out, reader, settings)
    try:
        delivered = notifier.notify(note)
    except Exception as exc:  # a notifier must not raise; if one does, it is a warning
        delivered = f"notifier failed: {type(exc).__name__}: {exc}"
    problems = [p for p in (problem, delivered) if p]
    if problems:
        warns = [{"check": "notify", "status": "WARN", "detail": p} for p in problems]
        out["warnings"] = [*out.get("warnings", []), *warns]
        _write(path, out)
    return out
