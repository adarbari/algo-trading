"""``algotrade-api``: serve the API with uvicorn on 127.0.0.1:8000 (``--reload`` for dev).
With ``ALGOTRADE_AUTH=off`` (no token, ADR 0040) it refuses a non-loopback ``--host``.
``algotrade-api schedule`` writes the launchd agent that keeps it serving on this Mac
(``ops/schedule.py``, ADR 0043) and prints the commands to install it; it never installs."""

import argparse
import json
from pathlib import Path

import uvicorn

from algotrade.config.env import auth_mode, load_dotenv
from algotrade.core.model.errors import ConfigurationError
from algotrade_api.auth.local import require_loopback
from algotrade_api.auth.mode import AuthMode
from algotrade_api.ops.schedule import DEFAULT_PORT, HOST, LABEL, api_plist

APP = "algotrade_api.app:app"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="algotrade-api", description=__doc__)
    parser.add_argument("--host", default=HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--reload", action="store_true", help="restart on code changes (dev)")
    sub = parser.add_subparsers(dest="command")
    sc = sub.add_parser(
        "schedule", help="write a launchd agent that keeps the API serving (not installed)"
    )
    sc.add_argument("--port", type=int, default=DEFAULT_PORT, dest="agent_port")
    sc.add_argument("--out", type=Path, default=Path("var") / f"{LABEL}.plist")
    return parser


def write_schedule(out: Path, port: int) -> dict[str, object]:
    """Write the agent for the checkout in the working directory; what to run to install it."""
    repo = Path.cwd().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(api_plist(repo, port))
    target = Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"
    plan: dict[str, object] = {
        "written": str(out),
        "serves": f"http://{HOST}:{port}",
        "install": [
            f"mkdir -p {repo / 'var' / 'logs'}",
            f"launchctl unload {target} 2>/dev/null || true",
            f"cp {out.resolve()} {target}",
            f"launchctl load {target}",
        ],
        "uninstall": [f"launchctl unload {target}", f"rm {target}"],
        "runbook": "docs/hosting.md",
    }
    if auth_mode() == AuthMode.OFF:
        plan["note"] = (
            "ALGOTRADE_AUTH=off: callers through Tailscale Funnel get 401 on every API call; "
            "set ALGOTRADE_AUTH=supabase in .env before hosting (docs/hosting.md)"
        )
    return plan


def main(argv: list[str] | None = None) -> None:
    parser = _parser()
    args = parser.parse_args(argv)
    load_dotenv()
    if args.command == "schedule":
        print(json.dumps(write_schedule(args.out, args.agent_port), indent=2))
        return
    if auth_mode() == AuthMode.OFF:
        try:
            require_loopback(args.host)
        except ConfigurationError as exc:
            parser.error(str(exc))
    uvicorn.run(APP, host=args.host, port=args.port, reload=args.reload)
