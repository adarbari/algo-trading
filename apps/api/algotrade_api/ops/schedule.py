"""Generate the macOS launchd agent that keeps the API serving on this Mac (ADR 0044).

The file is only written, never installed: loading it changes the machine's configuration,
so the owner runs ``launchctl load`` themselves (as for the nightly,
``algotrade_ingestion/ops/schedule.py``). The agent runs ``algotrade-api`` from the checkout's
venv with the checkout as its working directory, so the CLI reads the checkout's ``.env``
exactly as the nightly does; it binds a loopback address only (Tailscale Funnel forwards to
it), starts at login (``RunAtLoad``) and is restarted by launchd whenever it exits
(``KeepAlive``). Logs go to ``var/logs/api.log`` and ``api.err.log``.
"""

import plistlib
from pathlib import Path

LABEL = "com.algotrade.api"
HOST = "127.0.0.1"  # loopback only: Funnel (or a browser on this Mac) is the way in
DEFAULT_PORT = 8000


def api_plist(repo: Path, port: int = DEFAULT_PORT) -> bytes:
    """The agent for the checkout at ``repo`` serving on ``127.0.0.1:port``."""
    if not 0 < port < 65536:
        raise ValueError(f"invalid port {port}")
    logs = repo / "var" / "logs"
    agent: dict[str, object] = {
        "Label": LABEL,
        "ProgramArguments": [
            str(repo / ".venv" / "bin" / "algotrade-api"),
            "--host",
            HOST,
            "--port",
            str(port),
        ],
        "WorkingDirectory": str(repo),  # the CLI loads this checkout's .env
        "RunAtLoad": True,  # at login / boot
        "KeepAlive": True,  # restarted whenever it exits (launchd throttles a crash loop)
        "StandardOutPath": str(logs / "api.log"),
        "StandardErrorPath": str(logs / "api.err.log"),
    }
    return plistlib.dumps(agent)
