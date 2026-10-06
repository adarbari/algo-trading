"""Which exchange sessions a nightly run ingests, in order (ADR 0039).

Every session after the last nightly that finished done (SUCCEEDED, or COMPLETE / PARTIAL
in records written before ADR 0039), up to the last closed session
(``core/calendar.last_closed_session``), oldest first. A FAILED or WAITING nightly (ADR 0043: a
source has not published the session yet) does not count as done, so its session comes first
and is retried; the run stops at a session that fails or waits again (``nightly.run_nightly``),
so a later session never runs past it and lookback windows never span a gap. One run takes at
most ``max_catch_up`` sessions, the oldest; the others wait for the next run (the hourly
watchdog). No session is dropped: a dropped session would leave a permanent gap in the bars.
With no earlier nightly, only the last closed one.
"""

from dataclasses import dataclass, field
from datetime import date

from algotrade.core.time.calendar import next_session, sessions_between
from algotrade.storage.tables.writers import StoreWriter
from algotrade_ingestion.tasks.framework.run import last_finished_session

NIGHTLY_RUN = "nightly"  # the job name of the per-session nightly run records


@dataclass(frozen=True)
class Plan:
    sessions: list[date]  # oldest first
    waiting: list[date] = field(default_factory=list)  # pending, for a later run (over the cap)
    last_done: date | None = None
    until: date | None = None  # the last closed session (latest-only steps run only for it)

    @property
    def latest(self) -> date | None:
        """The session latest-only steps run for: the last closed one, when this run has it."""
        last = self.until or (self.sessions[-1] if self.sessions else None)
        return last if last in self.sessions else None


def last_done(writer: StoreWriter) -> date | None:
    """The latest session a nightly finished done for (SUCCEEDED; COMPLETE / PARTIAL before
    ADR 0039: the run record stores SUCCEEDED as COMPLETE)."""
    return last_finished_session(writer, NIGHTLY_RUN)


def plan_sessions(last: date | None, until: date, max_catch_up: int) -> Plan:
    """Sessions after ``last`` up to ``until`` (inclusive), the oldest ``max_catch_up``."""
    if last is None:
        return Plan([until], until=until)
    if last >= until:
        return Plan([], last_done=last, until=until)
    pending = sessions_between(next_session(last), until)
    cap = max(1, max_catch_up)
    return Plan(pending[:cap], pending[cap:], last, until)
