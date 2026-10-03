"""After a nightly run: write its summary file, and notify when it is not COMPLETE.

``Notifier`` is a small interface; the default on macOS is a desktop notification through
``osascript`` (never under pytest). ``config/site/nightly.toml`` ``[notify]`` turns it off or
moves the summary file (``var/logs/nightly-latest.json`` by default).
"""

import json
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Protocol

from algotrade.config.site.settings import NightlySettings

TITLE = "algotrade nightly"


class Notifier(Protocol):
    def notify(self, title: str, message: str) -> None: ...


class NullNotifier:
    def notify(self, title: str, message: str) -> None:
        return None


class MacNotifier:
    """A macOS notification (``display notification``); failures are ignored."""

    def notify(self, title: str, message: str) -> None:
        script = f"display notification {_quote(message)} with title {_quote(title)}"
        subprocess.run(["osascript", "-e", script], check=False, timeout=10, capture_output=True)


def _quote(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def default_notifier(settings: NightlySettings) -> Notifier:
    """The desktop notifier on macOS when enabled, outside tests; else a no-op."""
    desktop = settings.notify_enabled and settings.notify_desktop
    if desktop and sys.platform == "darwin" and "pytest" not in sys.modules:
        return MacNotifier()
    return NullNotifier()


def message(summary: Mapping[str, Any]) -> str:
    """One line: status, sessions and the steps that did not complete."""
    bad = sorted(
        {
            f"{name} {step['status'].lower()}"
            for run in summary.get("runs", [])
            for name, step in run["steps"].items()
            if step["status"] in ("FAILED", "BLOCKED", "PARTIAL")
        }
        | {
            f"{name} {step['status'].lower()}"
            for name, step in summary.get("steps", {}).items()
            if step["status"] in ("FAILED", "BLOCKED", "PARTIAL")
        }
    )
    sessions = ", ".join(summary.get("sessions", [])) or "no session"
    return f"{summary['status']} ({sessions})" + (f": {'; '.join(bad)}" if bad else "")


def report(summary: Mapping[str, Any], settings: NightlySettings, notifier: Notifier) -> None:
    """Always write the summary file; notify when the status is not COMPLETE."""
    path = Path(settings.summary_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary, indent=2, default=str))
    if summary["status"] != "COMPLETE" and settings.notify_enabled:
        notifier.notify(TITLE, message(summary))
