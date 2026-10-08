"""``algotrade-api``: serve the API with uvicorn on 127.0.0.1:8000 (``--reload`` for dev).
With ``ALGOTRADE_AUTH=off`` (no token, ADR 0040) it refuses a non-loopback ``--host``.
``algotrade-api schedule`` writes the launchd agent that keeps it serving on this Mac
(``ops/schedule.py``, ADR 0044) and prints the commands to install it; it never installs.
``algotrade-api stamp-web <dist>`` stamps a web build with the checkout it was built from
(``make web-build`` runs it) and says when the running API is out of step with it
(``ops/build.py``): it prints the restart command, never runs it. ``schedule --agent deploy``
writes the auto-deploy agent; ``deploy-plan`` and ``deploy-verify`` are what
``scripts/ops/deploy.sh`` asks (``ops/deploy.py``, ADR 0057)."""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

import uvicorn

from algotrade.config.env import auth_mode, load_dotenv, port_base
from algotrade.core.model.errors import ConfigurationError
from algotrade_api.auth.local import require_loopback
from algotrade_api.auth.mode import AuthMode
from algotrade_api.ops.build import Fetch, fetch_http, running_mismatches, write_web_stamp
from algotrade_api.ops.deploy import CHECKS, actions, verify
from algotrade_api.ops.schedule import (
    DEFAULT_PORT,
    DEPLOY_LABEL,
    HOST,
    LABEL,
    api_plist,
    deploy_plist,
)

APP = "algotrade_api.app:app"


def serve_port() -> int:
    """The port ``algotrade-api`` serves on: this worktree's block (``ALGOTRADE_PORT_BASE``, set
    by ``scripts/worktree.sh``) else 8000. The launchd agent keeps 8000 (``schedule``)."""
    return port_base(DEFAULT_PORT)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="algotrade-api", description=__doc__)
    parser.add_argument("--host", default=HOST)
    parser.add_argument("--port", type=int, default=serve_port())
    parser.add_argument("--reload", action="store_true", help="restart on code changes (dev)")
    sub = parser.add_subparsers(dest="command")
    sc = sub.add_parser(
        "schedule", help="write a launchd agent that keeps the API serving (not installed)"
    )
    sc.add_argument("--port", type=int, default=DEFAULT_PORT, dest="agent_port")
    sc.add_argument("--out", type=Path, default=None, help="default var/<label>.plist")
    sc.add_argument("--agent", choices=("api", "deploy"), default="api")
    dp = sub.add_parser("deploy-plan", help="what a deploy of the commits A..B must run")
    dp.add_argument("--since", required=True)
    dp.add_argument("--to", required=True)
    dv = sub.add_parser("deploy-verify", help="wait until the running site is at a commit")
    dv.add_argument("--expect", required=True)
    dv.add_argument("--check", choices=CHECKS, default="full")
    dv.add_argument("--port", type=int, default=DEFAULT_PORT, dest="agent_port")
    st = sub.add_parser("stamp-web", help="stamp a web build; say if the running API is behind it")
    st.add_argument("dist", type=Path)
    st.add_argument("--port", type=int, default=DEFAULT_PORT, dest="agent_port")
    return parser


def write_deploy_schedule(out: Path | None) -> dict[str, object]:
    """Write the auto-deploy agent for the checkout in the working directory, with this
    process's PATH (the one that finds uv, npm and git); what to run to install it."""
    repo = Path.cwd().resolve()
    out = out or Path("var") / f"{DEPLOY_LABEL}.plist"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(deploy_plist(repo, os.pathsep.join(os.get_exec_path())))
    target = Path.home() / "Library" / "LaunchAgents" / f"{DEPLOY_LABEL}.plist"
    return {
        "written": str(out),
        "polls": "origin/main every 300 s (scripts/ops/deploy.sh --auto)",
        "install": [
            f"mkdir -p {repo / 'var' / 'logs'}",
            f"launchctl bootout gui/{os.getuid()}/{DEPLOY_LABEL} 2>/dev/null || true",
            f"cp {out.resolve()} {target}",
            f"launchctl bootstrap gui/{os.getuid()} {target}",
        ],
        "uninstall": [f"launchctl bootout gui/{os.getuid()}/{DEPLOY_LABEL}", f"rm {target}"],
        "runbook": "docs/hosting.md",
    }


def changed_paths(since: str, to: str) -> list[str]:
    """The files that differ between two commits of the checkout in the working directory."""
    done = subprocess.run(
        ["git", "diff", "--name-only", f"{since}..{to}"],
        capture_output=True,
        text=True,
        check=True,
    )
    return done.stdout.split()


def write_schedule(out: Path | None, port: int) -> dict[str, object]:
    """Write the agent for the checkout in the working directory; what to run to install it."""
    repo = Path.cwd().resolve()
    out = out or Path("var") / f"{LABEL}.plist"
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


def stamp_web(dist: Path, port: int, fetch: Fetch | None = None) -> list[str]:
    """Stamp the build in ``dist``; the lines to print: the stamp, then what the API on ``port``
    reports out of step (a running API keeps its schema until restarted)."""
    stamp = write_web_stamp(dist)
    lines = [f"stamped {dist}: commit {stamp.git_sha[:9]}, GraphQL schema {stamp.schema_hash}"]
    url = f"http://{HOST}:{port}"
    found = running_mismatches(url) if fetch is None else running_mismatches(url, fetch)
    if found is None:
        lines.append(f"no API answering at {url}")
    elif found:
        lines += [f"WARNING: the API at {url} is out of step:", *(f"  - {m}" for m in found)]
    else:
        lines.append(f"the API at {url} serves this build's schema and commit")
    return lines


def main(argv: list[str] | None = None) -> None:
    parser = _parser()
    args = parser.parse_args(argv)
    load_dotenv()
    if args.command == "schedule":
        plan = (
            write_deploy_schedule(args.out)
            if args.agent == "deploy"
            else write_schedule(args.out, args.agent_port)
        )
        print(json.dumps(plan, indent=2))
        return
    if args.command == "deploy-plan":
        print(" ".join(a.value for a in actions(changed_paths(args.since, args.to))))
        return
    if args.command == "deploy-verify":
        url = f"http://{HOST}:{args.agent_port}"
        problems = verify(url, args.expect, fetch_http, args.check)
        print("\n".join(problems))
        sys.exit(1 if problems else 0)
    if args.command == "stamp-web":
        print("\n".join(stamp_web(args.dist, args.agent_port)))
        return
    if auth_mode() == AuthMode.OFF:
        try:
            require_loopback(args.host)
        except ConfigurationError as exc:
            parser.error(str(exc))
    uvicorn.run(APP, host=args.host, port=args.port, reload=args.reload)
