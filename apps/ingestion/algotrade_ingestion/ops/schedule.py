"""Generate a macOS launchd agent that runs the nightly job and self-heals missed runs.

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
