"""Generate a macOS launchd agent that runs the nightly job on weekdays.

The file is only written, never installed: loading it changes the machine's configuration,
so the owner runs ``launchctl load`` themselves. launchd uses local time; the default 23:30
falls after the US close (16:00 New York) whether the machine is in New York or London.

``RunAtLoad`` is false: loading the agent (or logging in) does not start a run. If the
machine is asleep at the scheduled time, launchd starts the missed run when it wakes, which
may be during market hours. That is safe: without ``--date`` the nightly ingests only
sessions whose close has passed (``core/calendar.last_closed_session``) and catches up the
sessions missed since its last run (``workflows/nightly/sessions.py``).
"""

import plistlib
from pathlib import Path

LABEL = "com.algotrade.nightly"


def nightly_plist(repo: Path, hour: int, minute: int, export_dir: Path | None = None) -> bytes:
    if not (0 <= hour < 24 and 0 <= minute < 60):
        raise ValueError(f"invalid time {hour:02d}:{minute:02d}")
    command = [str(repo / ".venv" / "bin" / "algotrade-ingest"), "nightly"]
    if export_dir is not None:
        command += ["--export-dir", str(export_dir)]
    logs = repo / "var" / "logs"
    return plistlib.dumps(
        {
            "Label": LABEL,
            "ProgramArguments": command,
            "WorkingDirectory": str(repo),
            "RunAtLoad": False,
            "StartCalendarInterval": [
                {"Weekday": d, "Hour": hour, "Minute": minute} for d in range(1, 6)
            ],
            "StandardOutPath": str(logs / "nightly.log"),
            "StandardErrorPath": str(logs / "nightly.err.log"),
        }
    )
