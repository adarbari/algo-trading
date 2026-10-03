"""Which exchange sessions a nightly run ingests (catch-up after missed nights).

Every session after the last nightly that finished COMPLETE or PARTIAL, up to the last
closed session (``core/calendar.last_closed_session``), capped at the latest
``max_catch_up``. With no earlier nightly, only the last closed session. A FAILED nightly
does not count as done, so its sessions are retried.
"""

from dataclasses import dataclass, field
from datetime import date

from algotrade.core.calendar import next_session, sessions_between
from algotrade.storage.writers import StoreWriter
from algotrade_ingestion.tasks.framework.run import last_finished_session

NIGHTLY_RUN = "nightly"  # the job name of the per-session nightly run records


@dataclass(frozen=True)
class Plan:
    sessions: list[date]  # oldest first; the last one is the latest closed session
    dropped: list[date] = field(default_factory=list)  # missed, but over the catch-up cap
    last_done: date | None = None

    @property
    def latest(self) -> date | None:
        return self.sessions[-1] if self.sessions else None


def last_done(writer: StoreWriter) -> date | None:
    """The latest session a nightly finished COMPLETE or PARTIAL for."""
    return last_finished_session(writer, NIGHTLY_RUN)


def plan_sessions(last: date | None, until: date, max_catch_up: int) -> Plan:
    """Sessions after ``last`` up to ``until`` (inclusive), the latest ``max_catch_up``."""
    if last is None:
        return Plan([until])
    if last >= until:
        return Plan([], last_done=last)
    pending = sessions_between(next_session(last), until)
    cap = max(1, max_catch_up)
    return Plan(pending[-cap:], pending[:-cap], last)
