"""Site settings for the nightly workflow (``config/site/nightly.toml``): which sessions it
ingests, its alerts and notifications, and until when a step whose source has not published
the session yet waits instead of failing (ADR 0043)."""

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import time
from typing import Any

from algotrade.config.site.fields import Table
from algotrade.core.model.errors import ConfigurationError

CLOCK = re.compile(r"([01]\d|2[0-3]):([0-5]\d)")


def clock_time(table: Table, key: str, default: time) -> time:
    """``"HH:MM"`` as a time of day (``default`` when the key is missing)."""
    if key not in table.names():
        return default
    text = table.text(key, "")
    match = CLOCK.fullmatch(text)
    if match is None:
        raise ConfigurationError(f'{table.where} {key}: expected a time like "23:00", got {text!r}')
    return time(int(match[1]), int(match[2]))


@dataclass(frozen=True)
class NightlySettings:
    """``config/site/nightly.toml``: sessions, catch-up, the duration alert, notification."""

    settle_minutes: int = 30
    max_catch_up: int = 5
    max_duration_minutes: float = 40.0
    notify_enabled: bool = True
    notify_desktop: bool = True
    summary_path: str = "var/logs/nightly-latest.json"
    # [notify.email]: the daily summary email (addresses + credentials: config/env.py only)
    email_enabled: bool = False
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    email_max_examples: int = 5
    # [schedule] / [steps.<name>]: Los Angeles wall-clock time on the session's date
    data_deadline: time = time(23, 0)
    step_deadlines: Mapping[str, time] = field(default_factory=dict)
    # [steps.<name>] settle_minutes: wait this long after the close before fetching (0: no wait)
    step_settle_minutes: Mapping[str, int] = field(default_factory=dict)

    def deadline_for(self, step: str) -> time:
        return self.step_deadlines.get(step, self.data_deadline)

    def settle_for(self, step: str) -> int:
        return self.step_settle_minutes.get(step, 0)

    @classmethod
    def from_document(
        cls, doc: Mapping[str, Any] | None, where: str = "nightly.toml"
    ) -> "NightlySettings":
        d = cls()
        root = Table(doc, where)
        root.only(["sessions", "alerts", "notify", "schedule", "steps"])
        schedule = root.table("schedule", ["data_deadline"])
        declared = root.raw("steps") or {}
        steps_table = root.table("steps", list(declared))
        steps = {n: steps_table.table(n, ["deadline", "settle_minutes"]) for n in declared}
        sessions = root.table("sessions", ["settle_minutes", "max_catch_up"])
        alerts = root.table("alerts", ["max_duration_minutes"])
        notify = root.table("notify", ["enabled", "desktop", "summary_path", "email"])
        email = notify.table("email", ["enabled", "smtp_host", "smtp_port", "max_examples"])
        return cls(
            settle_minutes=sessions.integer("settle_minutes", d.settle_minutes, 0),
            max_catch_up=sessions.integer("max_catch_up", d.max_catch_up, 1),
            max_duration_minutes=alerts.number("max_duration_minutes", d.max_duration_minutes, 0),
            notify_enabled=notify.boolean("enabled", d.notify_enabled),
            notify_desktop=notify.boolean("desktop", d.notify_desktop),
            summary_path=notify.text("summary_path", d.summary_path),
            email_enabled=email.boolean("enabled", d.email_enabled),
            smtp_host=email.text("smtp_host", d.smtp_host),
            smtp_port=email.integer("smtp_port", d.smtp_port, 1),
            email_max_examples=email.integer("max_examples", d.email_max_examples, 0),
            data_deadline=clock_time(schedule, "data_deadline", d.data_deadline),
            step_deadlines={
                n: clock_time(t, "deadline", d.data_deadline)
                for n, t in steps.items()
                if "deadline" in t.names()
            },
            step_settle_minutes={
                n: t.integer("settle_minutes", 0, 0)
                for n, t in steps.items()
                if "settle_minutes" in t.names()
            },
        )
