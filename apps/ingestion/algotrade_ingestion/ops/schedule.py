"""Generate the macOS launchd agents: the nightly job (self-healing missed runs) and the monthly
Tiingo history fill.

The file is only written, never installed: loading it changes the machine's configuration,
so the owner runs ``launchctl load`` themselves. launchd uses local time; the default 15:00
is for an owner in Pacific time (the US close is 13:00 PT; 15:00 leaves margin past the
settle time in ``config/site/nightly.toml``).

Three triggers start ``algotrade-ingest nightly`` (no ``--date``):

- ``StartCalendarInterval``: weekdays at the scheduled time. A time missed while the Mac
  sleeps fires once on wake; a time missed while it is off does not fire at all, hence:
- ``RunAtLoad``: at login / boot (and when the agent is loaded).
- ``StartInterval``: a watchdog every ``watchdog_s`` seconds (0: none), for anything else
  that was missed. launchd never starts a second copy while one is running.

Repeated starts are cheap: without ``--date`` the nightly ingests only sessions whose close
plus settle has passed (``core/time/calendar.last_closed_session``), catches up the ones
missed since its last COMPLETE / PARTIAL run (``workflows/nightly/sessions.py``) and, when
there are none, exits 0 at once without a run record or a notification (``cli/main.py``).
"""

import plistlib
from pathlib import Path

LABEL = "com.algotrade.nightly"
DEFAULT_TIME = "15:00"  # local time (Pacific for the owner): close 13:00 PT + margin
DEFAULT_WATCHDOG_MINUTES = 60
# The owner's optional wake (run by them, never by this code): powers the Mac on / wakes it
# five minutes before the scheduled run on weekdays.
WAKE_COMMAND = "sudo pmset repeat wakeorpoweron MTWRF 14:55:00"


def nightly_plist(
    repo: Path,
    hour: int,
    minute: int,
    export_dir: Path | None = None,
    watchdog_s: int = DEFAULT_WATCHDOG_MINUTES * 60,
) -> bytes:
    if not (0 <= hour < 24 and 0 <= minute < 60):
        raise ValueError(f"invalid time {hour:02d}:{minute:02d}")
    if watchdog_s < 0:
        raise ValueError(f"invalid watchdog interval {watchdog_s} s")
    command = [str(repo / ".venv" / "bin" / "algotrade-ingest"), "nightly"]
    if export_dir is not None:
        command += ["--export-dir", str(export_dir)]
    logs = repo / "var" / "logs"
    agent: dict[str, object] = {
        "Label": LABEL,
        "ProgramArguments": command,
        "WorkingDirectory": str(repo),
        "RunAtLoad": True,  # login / boot: catch up whatever was missed while the Mac was off
        "StartCalendarInterval": [
            {"Weekday": d, "Hour": hour, "Minute": minute} for d in range(1, 6)
        ],
        "StandardOutPath": str(logs / "nightly.log"),
        "StandardErrorPath": str(logs / "nightly.err.log"),
    }
    if watchdog_s:
        agent["StartInterval"] = watchdog_s
    return plistlib.dumps(agent)


MONTHLY_LABEL = "com.algotrade.bars-history-monthly"
MONTHLY_FILL = (
    450  # = [tiingo] monthly_symbol_budget (free tier: 500 symbols a month, with a buffer)
)
MONTHLY_DAY, MONTHLY_TIME = 2, "19:00"  # the 2nd of each month, local time


def monthly_fill_plist(
    repo: Path, fill: int = MONTHLY_FILL, day: int = MONTHLY_DAY, hour: int = 19, minute: int = 0
) -> bytes:
    """The agent that runs ``algotrade-ingest bars-history --fill N --wait`` once a month: the
    next N names without Tiingo history (``services.events.fill``), within the month's symbol
    budget. 450 names at 72 s each hold the ingest lock about 9 hours, so it starts at 19:00,
    after the 15:00 nightly, and ends about 04:00 before the next one. ``--wait`` queues it
    behind a running ingest. A month the Mac is off through its time is skipped by launchd (the
    next month's run covers more: the budget is per month, not per
    run), or run it by hand (README "Long runs")."""
    if fill < 1:
        raise ValueError(f"invalid fill {fill}")
    if not (1 <= day <= 28 and 0 <= hour < 24 and 0 <= minute < 60):
        raise ValueError(f"invalid monthly time day {day} {hour:02d}:{minute:02d}")
    logs = repo / "var" / "logs"
    agent: dict[str, object] = {
        "Label": MONTHLY_LABEL,
        "ProgramArguments": [
            str(repo / ".venv" / "bin" / "algotrade-ingest"),
            "bars-history",
            "--fill",
            str(fill),
            "--wait",
        ],
        "WorkingDirectory": str(repo),
        "StartCalendarInterval": {"Day": day, "Hour": hour, "Minute": minute},
        "StandardOutPath": str(logs / "bars-history-monthly.log"),
        "StandardErrorPath": str(logs / "bars-history-monthly.err.log"),
    }
    return plistlib.dumps(agent)
