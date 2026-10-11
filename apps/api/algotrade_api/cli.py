"""``algotrade-api``: serve the API with uvicorn on 127.0.0.1:8000 (``--reload`` for dev).
With ``ALGOTRADE_AUTH=off`` (no token, ADR 0040) it refuses a non-loopback ``--host``.
``algotrade-api schedule`` writes the launchd agent that keeps it serving on this Mac
(``ops/schedule.py``, ADR 0044) and prints the commands to install it; it never installs.
``algotrade-api stamp-web <dist>`` stamps a web build with the checkout it was built from
(``make web-build`` runs it) and says when the running API is out of step with it
(``ops/build.py``): it prints the restart command, never runs it. ``schedule --agent deploy``
writes the auto-deploy agent; ``deploy-plan`` and ``deploy-verify`` are what
``scripts/ops/deploy.sh`` asks (``ops/deploy.py``, ADR 0057). Serving raises the process's
open-files soft limit to ``OPEN_FILES`` and caps the connections served at once at
``MAX_CONNECTIONS`` (``ops/schedule.py``: launchd's 256 ran out on 2026-10-08).
``algotrade-api golden run`` is the owner-run live evaluation of the drafting prompt against
the golden set (``ops/golden.py``: it calls real models and spends money, only with ``--yes``)."""

import argparse
import json
import os
import resource
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

import uvicorn

from algotrade.config.env import (
    auth_mode,
    config_dir,
    data_url,
    llm_off,
    load_dotenv,
    port_base,
    user_id,
)
from algotrade.config.site.settings import load_llm
from algotrade.config.user import DEFAULT_USER, UserContext
from algotrade.core.model.errors import ConfigurationError
from algotrade.services.drafting.screens import ScreenDraft, draft_screen
from algotrade.services.read.context import NotFoundError, ReadContext, open_context
from algotrade.services.text_model.model import TextModel
from algotrade_api.auth.local import require_loopback
from algotrade_api.auth.mode import AuthMode
from algotrade_api.deps import open_store
from algotrade_api.ops.build import Fetch, fetch_http, running_mismatches, write_web_stamp
from algotrade_api.ops.deploy import CHECKS, actions, holds_ingest, verify
from algotrade_api.ops.golden import (
    DEFAULT_BUDGET_USD,
    DEFAULT_MAX_CALLS,
    DEFAULT_REPEAT,
    GOLDEN_ROOT,
    SCREENER_ID,
    SPLITS,
    CostTap,
    RunArgs,
    run_golden,
)
from algotrade_api.ops.schedule import (
    DEFAULT_PORT,
    DEPLOY_LABEL,
    HOST,
    LABEL,
    MAX_CONNECTIONS,
    OPEN_FILES,
    api_plist,
    deploy_plist,
)
from algotrade_api.text_model import open_text_model

APP = "algotrade_api.app:app"


def serve_port() -> int:
    """The port ``algotrade-api`` serves on: this worktree's block (``ALGOTRADE_PORT_BASE``, set
    by ``scripts/worktree.sh``) else 8000. The launchd agent keeps 8000 (``schedule``)."""
    return port_base(DEFAULT_PORT)


def raise_open_files(wanted: int = OPEN_FILES) -> int:
    """Raise this process's open-files soft limit to ``wanted`` (never above the hard limit,
    never lowered); the soft limit it now has."""
    soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
    target = wanted if hard == resource.RLIM_INFINITY else min(wanted, hard)
    if soft != resource.RLIM_INFINITY and soft < target:
        resource.setrlimit(resource.RLIMIT_NOFILE, (target, hard))
        return target
    return soft


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
    dp.add_argument(
        "--locks", action="store_true", help="print `ingest` if the deploy needs the ingest lock"
    )
    dv = sub.add_parser("deploy-verify", help="wait until the running site is at a commit")
    dv.add_argument("--expect", required=True)
    dv.add_argument("--check", choices=CHECKS, default="full")
    dv.add_argument("--port", type=int, default=DEFAULT_PORT, dest="agent_port")
    st = sub.add_parser("stamp-web", help="stamp a web build; say if the running API is behind it")
    st.add_argument("dist", type=Path)
    st.add_argument("--port", type=int, default=DEFAULT_PORT, dest="agent_port")
    gd = sub.add_parser("golden", help="owner-run live evaluation of the drafting prompt")
    gsub = gd.add_subparsers(dest="golden_command", required=True)
    gr = gsub.add_parser("run", help="ask real models the golden cases and score the drafts")
    gr.add_argument("--cases", default="", help="case ids, comma separated (default: all)")
    gr.add_argument("--split", choices=SPLITS, default="all")
    gr.add_argument("--provider", action="append", default=[], help="llm.toml provider id")
    gr.add_argument("--repeat", type=int, default=DEFAULT_REPEAT)
    gr.add_argument("--record", action="store_true", help="write passing raw answers for CI replay")
    gr.add_argument("--force", action="store_true", help="--record may overwrite a file")
    gr.add_argument("--json", action="store_true", dest="as_json")
    gr.add_argument("--max-calls", type=int, default=DEFAULT_MAX_CALLS)
    gr.add_argument("--budget-usd", type=float, default=DEFAULT_BUDGET_USD)
    gr.add_argument("--user", default=None, help="user id asked as (default $ALGOTRADE_USER)")
    gr.add_argument("--yes", action="store_true", help="spend: without it only the plan is shown")
    return parser


def golden_run(args: argparse.Namespace) -> int:
    """``golden run``: wire the store, the user's context and one single-provider text model per
    provider into ``ops/golden.run_golden``; the exit code."""
    user = args.user or user_id(DEFAULT_USER)
    store = open_store(data_url(), config_dir(), UserContext(user))
    models: list[TextModel] = []
    holder: list[ReadContext] = []

    def open_models(ids: Sequence[str], costs: CostTap) -> dict[str, TextModel]:
        try:
            holder.append(open_context(store.reader, store.configs, UserContext(user)))
        except NotFoundError as exc:
            raise ConfigurationError(f"the store has no session to draft over: {exc}") from exc
        out: dict[str, TextModel] = {}
        for pid in ids:
            model, why = open_text_model(store.configs, data_url(), only=[pid], tee=costs.submit)
            if model is None:
                raise ConfigurationError(why)
            out[pid] = model
            models.append(model)
        return out

    def draft(model: TextModel, sentence: str) -> ScreenDraft:
        return draft_screen(holder[0], model, SCREENER_ID, sentence)

    def to_stderr(line: str) -> None:
        print(line, file=sys.stderr)

    run_args = RunArgs(
        tuple(c for c in args.cases.split(",") if c), args.split, tuple(args.provider),
        args.repeat, args.record, args.force, args.as_json, args.max_calls, args.budget_usd,
        args.yes,
    )  # fmt: skip
    try:
        return run_golden(
            run_args, load_llm(store.configs), llm_off(), Path.cwd() / GOLDEN_ROOT, open_models,
            draft, print, to_stderr if args.as_json else print,
        )  # fmt: skip
    finally:
        for model in models:
            getattr(model, "close", lambda: None)()


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
    if args.command == "golden":
        sys.exit(golden_run(args))
    if args.command == "deploy-plan":
        paths = changed_paths(args.since, args.to)
        if args.locks:
            print("ingest" if holds_ingest(paths) else "")
        else:
            print(" ".join(a.value for a in actions(paths)))
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
    raise_open_files()
    uvicorn.run(
        APP,
        host=args.host,
        port=args.port,
        reload=args.reload,
        limit_concurrency=MAX_CONNECTIONS,
    )
