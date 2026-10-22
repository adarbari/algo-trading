"""Site settings for the nightly workflow (``config/site/nightly.toml``): which sessions it
ingests, its alerts and notifications, the duration alert of the post-session workflow (ADR 0070),
until when a step whose source has not published
the session yet waits instead of failing (ADR 0043), and the tables whose backfill is declared
under way (ADR 0055 amendment 2026-10-20)."""

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, time
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
class HistoryCopySettings:
    """``[history_copy]``: which tables the nightly's ``history-copy`` step keeps a history
    copy of (ADR 0060) and the disk it may use."""

    enabled: bool = True
    market_prefix: str = ""  # every table under it, all years (nightly.toml names it; "": none)
    instrument_tables: tuple[str, ...] = ()  # the Explore charts' tables, the last years only
    event_tables: tuple[
        str, ...
    ] = ()  # events tables read per instrument over all time: every year
    recent_years: int = 2  # calendar years (the session's and the ones before) kept for those
    budget_gb: float = (
        2.0  # the instrument and event tables' copies together; one that would not fit is skipped
    )
    free_disk_floor_gb: float = (
        10.0  # no build below this much free disk (a rebuilt year exists twice)
    )

    @classmethod
    def from_table(cls, section: Table) -> "HistoryCopySettings":
        d = cls()
        return cls(
            enabled=section.boolean("enabled", d.enabled),
            market_prefix=section.text("market_prefix", d.market_prefix),
            instrument_tables=section.strings("instrument_tables", d.instrument_tables),
            event_tables=section.strings("event_tables", d.event_tables),
            recent_years=section.integer("recent_years", d.recent_years, 1),
            budget_gb=section.number("budget_gb", d.budget_gb, 0),
            free_disk_floor_gb=section.number("free_disk_floor_gb", d.free_disk_floor_gb, 0),
        )


TABLE_NAME = re.compile(r"rollups/[a-z_]+/[a-z0-9_]+@v\d+")


@dataclass(frozen=True)
class Backfilling:
    """One ``[backfilling]`` entry: a stored table whose history is still being filled, and the
    last UTC calendar date (wall clock) until which a screener short of coverage only for want
    of it is a WARN (ADR 0055 amendment 2026-10-20)."""

    until: date
    reason: str


def backfilling(section: Table) -> Mapping[str, Backfilling]:
    """``[backfilling]``: table name -> its window; each entry needs ``until`` and ``reason``."""
    found: dict[str, Backfilling] = {}
    for name in section.names():
        if not TABLE_NAME.fullmatch(name):
            raise ConfigurationError(
                f"{section.where}: {name!r} is not a rollup table name (rollups/<entity>/<name>@vN)"
            )
        entry = section.table(name, ["until", "reason"])
        text = entry.text("until", "")
        try:
            until = date.fromisoformat(text)
        except ValueError:
            raise ConfigurationError(
                f'{entry.where}: until: expected a date like "2026-11-03", got {text!r}'
            ) from None
        found[name] = Backfilling(until=until, reason=entry.line("reason"))
    return found


@dataclass(frozen=True)
class CompactionSettings:
    """``[compaction]``: the tables the ``compact-runs`` job may compact (ADR 0078) and how
    gently it works. Only merge-mode tables without a history copy (a fitness test). The wait
    before a swap's superseded files are swept is the storage's ``SWAP_GRACE_S``."""

    tables: tuple[str, ...] = ()  # nightly.toml names them (forward_returns@v2 today)
    nice: int = 10  # os.nice increment the job takes on, so the API's reads win CPU contests
    partition_seconds: float = 300.0  # a partition slower than this stops the run (slow disk)
    workers: int = 4  # worker processes, each compacting one partition at a time
    worker_arrow_threads: int = 1  # Arrow CPU and I/O threads of each worker

    @classmethod
    def from_table(cls, section: Table) -> "CompactionSettings":
        d = cls()
        return cls(
            tables=section.strings("tables", d.tables),
            nice=section.integer("nice", d.nice, 0),
            partition_seconds=section.number("partition_seconds", d.partition_seconds, 1),
            workers=section.integer("workers", d.workers, 1),
            worker_arrow_threads=section.integer("worker_arrow_threads", d.worker_arrow_threads, 1),
        )


@dataclass(frozen=True)
class NightlySettings:
    """``config/site/nightly.toml``: sessions, catch-up, the duration alert, notification."""

    settle_minutes: int = 30
    max_catch_up: int = 5
    max_duration_minutes: float = 40.0
    post_max_duration_minutes: float = 360.0  # [post]: the post-session workflow's duration alert
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
    history_copy: HistoryCopySettings = field(default_factory=HistoryCopySettings)
    compaction: CompactionSettings = field(default_factory=CompactionSettings)
    # [resources]: what a running ingest may take from the Mac that also serves the web
    arrow_cpu_threads: int = 2  # Arrow decode threads (the API caps itself at the same 2)
    arrow_io_threads: int = 4
    nice: int = 10  # os.nice of every ingest command (and so its workers): the API's reads win
    min_free_gb: float = 15.0  # the nightly refuses to start with less free on the data volume
    # [serving] release_reads: the API serves the listed operations from the current serving
    # release (ADR 0077); false: every read is live, as before the release existed (kill switch)
    release_reads: bool = True
    # [serving] publishing_delay_minutes: how long a newer session may be complete before the pages
    # say it is being published (ADR 0077 decision 7; counted from the run that completed it)
    publishing_delay_minutes: int = 15
    # [backfilling]: tables still being filled; a screener short only of them warns until `until`
    backfilling: Mapping[str, Backfilling] = field(default_factory=dict)

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
        root.only(
            [
                "sessions",
                "alerts",
                "notify",
                "schedule",
                "steps",
                "history_copy",
                "compaction",
                "post",
                "resources",
                "backfilling",
                "serving",
            ]
        )
        serving = root.table("serving", ["release_reads", "publishing_delay_minutes"])
        schedule = root.table("schedule", ["data_deadline"])
        declared = root.raw("steps") or {}
        steps_table = root.table("steps", list(declared))
        steps = {n: steps_table.table(n, ["deadline", "settle_minutes"]) for n in declared}
        sessions = root.table("sessions", ["settle_minutes", "max_catch_up"])
        alerts = root.table("alerts", ["max_duration_minutes"])
        post = root.table("post", ["max_duration_minutes"])
        notify = root.table("notify", ["enabled", "desktop", "summary_path", "email"])
        email = notify.table("email", ["enabled", "smtp_host", "smtp_port", "max_examples"])
        resources = root.table(
            "resources", ["arrow_cpu_threads", "arrow_io_threads", "min_free_gb", "nice"]
        )
        history_copy = HistoryCopySettings.from_table(
            root.table(
                "history_copy",
                [
                    *("enabled", "market_prefix", "instrument_tables", "event_tables"),
                    "recent_years",
                    *("budget_gb", "free_disk_floor_gb"),
                ],
            )
        )
        declared_backfills = root.raw("backfilling") or {}
        if not isinstance(declared_backfills, Mapping):
            raise ConfigurationError(f"{where} backfilling: expected a table")
        compaction = CompactionSettings.from_table(
            root.table(
                "compaction",
                [
                    *("tables", "nice"),
                    *("partition_seconds", "workers", "worker_arrow_threads"),
                ],
            )
        )
        return cls(
            backfilling=backfilling(root.table("backfilling", list(declared_backfills))),
            history_copy=history_copy,
            compaction=compaction,
            release_reads=serving.boolean("release_reads", d.release_reads),
            publishing_delay_minutes=serving.integer(
                "publishing_delay_minutes", d.publishing_delay_minutes, 0
            ),
            arrow_cpu_threads=resources.integer("arrow_cpu_threads", d.arrow_cpu_threads, 1),
            nice=resources.integer("nice", d.nice, 0),
            arrow_io_threads=resources.integer("arrow_io_threads", d.arrow_io_threads, 1),
            min_free_gb=resources.number("min_free_gb", d.min_free_gb, 0),
            settle_minutes=sessions.integer("settle_minutes", d.settle_minutes, 0),
            max_catch_up=sessions.integer("max_catch_up", d.max_catch_up, 1),
            max_duration_minutes=alerts.number("max_duration_minutes", d.max_duration_minutes, 0),
            post_max_duration_minutes=post.number(
                "max_duration_minutes", d.post_max_duration_minutes, 0
            ),
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
