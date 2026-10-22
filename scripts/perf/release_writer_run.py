"""ADR 0077 decision 24 measurement: the serving release under a writer, on a CLONE of the store.

By hand, on an idle machine, NEVER in CI and never while ingest or compaction runs. Steps:
(1) refuse without ``--confirm-paused`` (the operator has confirmed nothing ingests or
compacts); (2) clone the real store's data dir with APFS copy-on-write (``cp -c -R``) into
``--dest`` (outside the repo and ``var/``; same volume; free space >= ``--min-free-gb``);
(3) ``algotrade-ingest serve-release --rebuild`` against the CLONE so CURRENT exists there;
(4) start ``algotrade-api --port <spare>`` on the clone (``ALGOTRADE_AUTH=off``; spare port =
``ALGOTRADE_PORT_BASE`` + ``PORT_OFFSET``); (5) ``load.py realistic --writer-store <clone>
--publish-every 120`` with ``serving.release_reads`` true, then false (two copies of the site
config in ``--dest``, selected by ``ALGOTRADE_CONFIG_DIR``; ``config/site`` is never edited),
then ``load.py cold`` right after restarting the API; (6) ``summary.json`` + ``summary.md`` in
``--dest/results`` with the pass / fail against ``load.CRITERIA`` and the decision 24 triggers;
(7) the API it started is always stopped, and nothing outside ``--dest`` is deleted (nothing
is deleted at all: remove ``--dest`` yourself afterwards).

``--dry-run`` prints the plan and runs only the read-only guards. A ``--dest`` or data URL that
resolves into the real store, ``var/`` or the repo is refused. Runbook:
docs/perf/release-writer-run.md.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

REPO = Path(__file__).resolve().parents[2]
PORT_OFFSET = 7  # the spare port: ALGOTRADE_PORT_BASE + 7 (a worktree's block is 20 wide)
PUBLISH_EVERY_S = 120
MIN_FREE_GB = 20.0
HEALTH_WAIT_S = 180.0
TRIGGERS = {  # ADR 0077 decision 24: any of these keeps the release reads off the shared path
    "page_p95_s": 2.5,  # fails above
    "health_p99_s": 0.25,  # fails at or above
    "cold_p95_s": 1.0,  # first 5 minutes after a restart; fails above
}
RELEASE_READS = re.compile(r"^(release_reads\s*=\s*)\w+", re.M)


class RefusalError(Exception):
    """A guard stopped the run before anything was changed."""


def file_path(url: str) -> Path:
    """The directory a ``file://`` data URL names (relative paths resolve against the cwd)."""
    parsed = urlparse(url)
    if parsed.scheme != "file":
        raise RefusalError(f"data URL {url!r}: only file:// stores are cloned")
    return Path(parsed.netloc + parsed.path).expanduser().resolve()


def _inside(path: Path, root: Path) -> bool:
    return path == root or root in path.parents


def check_paths(dest: Path, source: Path, clone: Path, repo: Path = REPO) -> None:
    """Refuse a ``dest`` or clone that is in (or is) the real store, ``var/`` or the repo."""
    dest, source, clone = dest.resolve(), source.resolve(), clone.resolve()
    var_roots = {repo / "var"} | {p for p in (source, source.parent) if p.name == "var"}
    if _inside(dest, repo) or _inside(dest, source) or _inside(source, dest):
        raise RefusalError(f"--dest {dest} is inside the repo or overlaps the real store {source}")
    if any(_inside(dest, v) for v in var_roots):
        raise RefusalError(f"--dest {dest} is inside a var/ directory")
    if clone == source or _inside(clone, source) or not _inside(clone, dest):
        raise RefusalError(f"clone {clone} must be inside --dest and never the real store")
    if dest.exists() and any(dest.iterdir()):
        raise RefusalError(f"--dest {dest} exists and is not empty (nothing is overwritten)")


def spare_port(env: dict[str, str], is_free: Callable[[int], bool]) -> int:
    """``ALGOTRADE_PORT_BASE`` + ``PORT_OFFSET``; refused without a base or when taken."""
    raw = env.get("ALGOTRADE_PORT_BASE", "")
    if not raw.isdigit():
        raise RefusalError("ALGOTRADE_PORT_BASE is not set: `source worktree.env` first")
    port = int(raw) + PORT_OFFSET
    if not is_free(port):
        raise RefusalError(f"port {port} (ALGOTRADE_PORT_BASE + {PORT_OFFSET}) is already in use")
    return port


def port_is_free(port: int) -> bool:
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", port)) != 0


def is_apfs(path: Path, run: Callable[..., subprocess.CompletedProcess]) -> bool:
    """True when ``diskutil info`` says the volume of ``path`` is APFS."""
    done = run(["diskutil", "info", str(path)], capture_output=True, text=True, check=False)
    return done.returncode == 0 and "apfs" in done.stdout.lower()


def check_clone_possible(
    source: Path,
    dest_parent: Path,
    min_free_gb: float,
    run: Callable[..., subprocess.CompletedProcess],
    usage: Callable[[Path], object] = shutil.disk_usage,
    device: Callable[[Path], int] = lambda p: p.stat().st_dev,
) -> None:
    """Refuse unless ``source`` and ``dest_parent`` share one APFS volume with room to spare."""
    if device(source) != device(dest_parent):
        raise RefusalError(
            "--dest is not on the same volume as the store: a copy-on-write clone needs it"
        )
    if not is_apfs(source, run):
        raise RefusalError(
            "the store is not on APFS: refusing (a full copy would be slow and large)"
        )
    free_gb = usage(dest_parent).free / 1e9  # type: ignore[attr-defined]
    if free_gb < min_free_gb:
        raise RefusalError(
            f"free space {free_gb:.1f} GB < floor {min_free_gb:g} GB (--min-free-gb)"
        )


def config_copy(site_config: Path, to: Path, release_reads: bool) -> Path:
    """A config root at ``to`` (its ``site/`` copied) whose ``[serving] release_reads`` is set."""
    shutil.copytree(site_config / "site", to / "site")
    nightly = to / "site" / "nightly.toml"
    text = nightly.read_text()
    if not RELEASE_READS.search(text):
        raise RefusalError(f"{nightly}: no release_reads line to override")
    nightly.write_text(RELEASE_READS.sub(rf"\g<1>{str(release_reads).lower()}", text, count=1))
    return to


def level_numbers(report: dict) -> dict[str, float]:
    """The worst page p95 and /health p99 over the levels of one load.py report."""
    levels = report.get("levels", [])
    page = max((p["p95"] for lv in levels for p in lv["pages"].values()), default=0.0)
    health = max((lv.get("health", {}).get("p99", 0.0) for lv in levels), default=0.0)
    return {"page_p95_s": page, "health_p99_s": health}


def judge(runs: dict[str, dict]) -> dict:
    """Pass / fail per run against the decision 24 triggers; ``runs`` maps label -> report."""
    out: dict[str, dict] = {}
    for label, report in runs.items():
        n = level_numbers(report)
        checks = {"page_p95_s": n["page_p95_s"] <= TRIGGERS["page_p95_s"]}
        if label.startswith("cold"):
            checks = {"cold_p95_s": n["page_p95_s"] <= TRIGGERS["cold_p95_s"]}
        else:
            checks["health_p99_s"] = n["health_p99_s"] < TRIGGERS["health_p99_s"]
        out[label] = {
            **n,
            "checks": checks,
            "load_pass": [lv.get("pass") for lv in report.get("levels", [])],
            "pass": all(checks.values()),
        }
    return out


def render_markdown(summary: dict) -> str:
    lines = [
        f"# Release-reads run {summary['when']}",
        "",
        f"clone `{summary['clone']}`, API port {summary['port']}; "
        f"decision 24 triggers: {json.dumps(TRIGGERS)}",
        "",
        "| run | page p95 s | /health p99 s | verdict |",
        "|---|---|---|---|",
    ]
    for label, v in summary["verdicts"].items():
        mark = "PASS" if v["pass"] else "FAIL"
        lines.append(f"| {label} | {v['page_p95_s']:.3g} | {v['health_p99_s']:.3g} | {mark} |")
    lines += ["", f"overall: {'PASS' if summary['pass'] else 'FAIL'}", ""]
    return "\n".join(lines)


@dataclass
class Tools:
    """What the run calls outside the process; tests pass fakes."""

    run: Callable[..., subprocess.CompletedProcess] = subprocess.run
    popen: Callable[..., subprocess.Popen] = subprocess.Popen
    healthy: Callable[[int], bool] = lambda port: _health(port)  # noqa: PLW0108
    sleep: Callable[[float], None] = time.sleep
    is_free: Callable[[int], bool] = port_is_free
    usage: Callable[[Path], object] = shutil.disk_usage
    device: Callable[[Path], int] = lambda p: p.stat().st_dev
    env: dict[str, str] = field(default_factory=lambda: dict(os.environ))
    log: Callable[[str], None] = print


def _health(port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=2) as r:
            return r.status == 200
    except OSError:
        return False


def plan_lines(args: argparse.Namespace, port: int, clone: Path) -> list[str]:
    clone_url = f"file://{clone}"
    url = f"http://127.0.0.1:{port}"
    load = f"load.py --url {url} --users {' '.join(map(str, args.users))} --seconds {args.seconds}"
    return [
        "1. require --confirm-paused (no ingest / compaction running)",
        f"2. cp -c -R {args.source_path} {clone}   (APFS clone; free >= {args.min_free_gb:g} GB)",
        "3. algotrade-ingest serve-release --rebuild   (ALGOTRADE_DATA_URL = the clone)",
        f"4. algotrade-api --port {port}   (ALGOTRADE_AUTH=off, clone, config-on)",
        f"5a. {load} --scenario realistic --writer-store {clone_url} "
        f"--publish-every {PUBLISH_EVERY_S}  (release_reads=true)",
        "5b. restart the API on config-off (release_reads=false), same load",
        f"5c. restart the API on config-on, then at once: {load} --scenario cold",
        f"6. write summary.json and summary.md in {args.dest}/results",
        "7. stop the API; delete nothing (remove --dest yourself)",
    ]


@contextlib.contextmanager
def api_process(tools: Tools, port: int, env: dict[str, str], log: Path) -> Iterator[None]:
    """The API on the clone, stopped on exit whatever happened."""
    with log.open("ab") as out:
        proc = tools.popen(
            [str(REPO / ".venv/bin/algotrade-api"), "--port", str(port)],
            env=env,
            stdout=out,
            stderr=subprocess.STDOUT,
        )
        try:
            deadline = time.monotonic() + HEALTH_WAIT_S
            while not tools.healthy(port):
                if proc.poll() is not None or time.monotonic() > deadline:
                    raise RuntimeError(f"the API on port {port} did not become healthy ({log})")
                tools.sleep(1.0)
            yield
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=30)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=30)


def load_run(tools: Tools, args: argparse.Namespace, port: int, extra: list[str]) -> dict:
    """One load.py run (its report path is the ``written`` line it prints); the report."""
    cmd = [
        sys.executable,
        str(REPO / "scripts/perf/load.py"),
        "--url",
        f"http://127.0.0.1:{port}",
        "--users",
        *map(str, args.users),
        "--seconds",
        str(args.seconds),
        *extra,
    ]
    done = tools.run(cmd, capture_output=True, text=True, env=tools.env, check=False)
    match = re.search(r"^written (\S+)$", done.stdout or "", re.M)
    if done.returncode != 0 or not match:
        raise RuntimeError(f"load.py failed ({done.returncode}): {(done.stderr or '')[-400:]}")
    return json.loads((REPO / match.group(1)).read_text())


def execute(args: argparse.Namespace, tools: Tools) -> int:
    dest = Path(args.dest).resolve()
    source = file_path(args.source_url)
    clone = dest / "data"
    clone_url = f"file://{clone}"
    args.source_path = source
    check_paths(dest, source, clone)
    port = spare_port(tools.env, tools.is_free)
    check_clone_possible(
        source, dest.parent, args.min_free_gb, tools.run, tools.usage, tools.device
    )
    for line in plan_lines(args, port, clone):
        tools.log(line)
    if args.dry_run:
        tools.log("dry run: nothing was changed")
        return 0
    if not args.confirm_paused:
        raise RefusalError(
            "pass --confirm-paused once the Backfill session confirms no ingest or "
            "compaction is running"
        )
    dest.mkdir(parents=True)
    (dest / "results").mkdir()
    done = tools.run(["cp", "-c", "-R", str(source), str(clone)], check=False)
    if done.returncode != 0:
        raise RuntimeError("the copy-on-write clone failed (is the store on this APFS volume?)")
    on = config_copy(REPO / "config", dest / "config-on", True)
    off = config_copy(REPO / "config", dest / "config-off", False)
    base = {**tools.env, "ALGOTRADE_DATA_URL": clone_url, "ALGOTRADE_AUTH": "off"}
    env_on = {**base, "ALGOTRADE_CONFIG_DIR": str(on)}
    env_off = {**base, "ALGOTRADE_CONFIG_DIR": str(off)}
    rebuilt = tools.run(
        [str(REPO / ".venv/bin/algotrade-ingest"), "serve-release", "--rebuild"],
        env=env_on,
        check=False,
    )
    if rebuilt.returncode != 0:
        raise RuntimeError(f"serve-release --rebuild failed ({rebuilt.returncode})")
    writer = [
        "--scenario",
        "realistic",
        "--writer-store",
        clone_url,
        "--publish-every",
        str(PUBLISH_EVERY_S),
    ]
    reports: dict[str, dict] = {}
    log = dest / "results" / "api.log"
    try:
        for label, env in (
            ("realistic+writer release_reads=true", env_on),
            ("realistic+writer release_reads=false", env_off),
        ):
            tools.env = env  # load.py's writer opens the clone through the same env
            with api_process(tools, port, env, log):
                reports[label] = load_run(tools, args, port, writer)
        tools.env = env_on
        with api_process(tools, port, env_on, log):  # the restart is the cold start
            reports["cold after restart"] = load_run(tools, args, port, ["--scenario", "cold"])
    finally:
        (dest / "results" / "reports.json").write_text(json.dumps(reports, indent=2))
    verdicts = judge(reports)
    summary = {
        "when": datetime.now(UTC).isoformat(),
        "clone": str(clone),
        "port": port,
        "triggers": TRIGGERS,
        "verdicts": verdicts,
        "pass": all(v["pass"] for v in verdicts.values()),
    }
    (dest / "results" / "summary.json").write_text(json.dumps(summary, indent=2))
    (dest / "results" / "summary.md").write_text(render_markdown(summary))
    tools.log(render_markdown(summary))
    return 0 if summary["pass"] else 1


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    p.add_argument("--dest", required=True, help="new throwaway dir outside the repo and var/")
    p.add_argument(
        "--source-url",
        default=os.environ.get("ALGOTRADE_DATA_URL", "file://./var/data"),
        help="the real store to clone (read only)",
    )
    p.add_argument(
        "--confirm-paused",
        action="store_true",
        help="the operator confirmed that no ingest or compaction runs",
    )
    p.add_argument("--dry-run", action="store_true", help="print the plan, change nothing")
    p.add_argument("--min-free-gb", type=float, default=MIN_FREE_GB)
    p.add_argument("--users", type=int, nargs="+", default=[100, 200])
    p.add_argument("--seconds", type=int, default=300, help="per level (covers 2+ publishes)")
    return p


def main(argv: list[str] | None = None, tools: Tools | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        return execute(args, tools or Tools())
    except RefusalError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
