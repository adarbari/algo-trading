"""`make doctor`: is this machine ready to work in the repo? Prints one line per check and the
exact fix command for each failure. Exits non-zero only on hard failures (warnings and info
never fail it). Every probe goes through `Probes`, so tests pass fakes. Never prints .env values.
"""

from __future__ import annotations

import json
import os
import plistlib
import re
import shutil
import socket
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

REPO = Path(__file__).resolve().parents[1]
CI_PYTHON = "3.12"
NODE_MAJOR = "24"
OK, FAIL, WARN, INFO = "ok", "FAIL", "warn", "info"
LOW_DISK_GB = 10  # below this a full disk stops every agent and the nightly (2026-10-06)
MAX_MERGED_WORKTREES = 10  # leftover worktrees of merged PRs, each with its own node_modules


def _run(cmd: list[str], cwd: Path | None = None) -> tuple[int, str]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, check=False, cwd=cwd, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 127, str(exc)
    return p.returncode, (p.stdout + p.stderr).strip()


def _main_checkout(repo: Path = REPO) -> Path:
    """The main checkout (the one owning ``.git``), also when ``repo`` is a worktree."""
    rc, out = _run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"], cwd=repo)
    return Path(out).parent if rc == 0 and out else repo


def _port_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.5):
            return True
    except OSError:
        return False


API_URL = "http://127.0.0.1:8000"  # the launchd agent's address (ADR 0044)


def _api_build() -> tuple[str, ...] | None:
    """What the API on 8000 reports out of step (``algotrade_api.ops.build``); None: no API."""
    from algotrade_api.ops.build import running_mismatches  # noqa: PLC0415 (venv may lack it)

    return running_mismatches(API_URL)


@dataclass
class Probes:
    """The machine, as the checks see it. Defaults are real; tests override."""

    repo: Path = REPO
    which: Callable[[str], str | None] = shutil.which
    run: Callable[..., tuple[int, str]] = _run
    port_open: Callable[[str, int], bool] = _port_open
    env_keys: Callable[[], set[str]] = field(default=set)
    data_url: Callable[[], str] = field(default=lambda: "file://./var/data")
    main: Callable[[], Path] = _main_checkout
    required: tuple[str, ...] = ()
    web_dist: Callable[[], Path | None] = field(default=lambda: None)  # ALGOTRADE_WEB_DIST
    llm_error: Callable[[Path], str | None] = field(default=lambda main: None)  # llm.toml's error
    launch_agents: Path = Path.home() / "Library" / "LaunchAgents"
    free_bytes: Callable[[Path], int] = lambda path: shutil.disk_usage(path).free
    api_build: Callable[[], tuple[str, ...] | None] = field(default=_api_build)


@dataclass(frozen=True)
class Result:
    level: str
    name: str
    detail: str
    fix: str = ""


def check_uv(p: Probes) -> Result:
    if p.which("uv"):
        return Result(OK, "uv", "on PATH")
    return Result(
        FAIL, "uv", "not on PATH (make install / check / lock-check need it)", "brew install uv"
    )


def check_node(p: Probes) -> Result:
    if not p.which("node"):
        return Result(FAIL, "node", "not on PATH", f"brew install node@{NODE_MAJOR}")
    _, out = p.run(["node", "--version"])
    if out.lstrip("v").split(".")[0] == NODE_MAJOR:
        return Result(OK, "node", out)
    return Result(
        FAIL, "node", f"{out or 'unknown'}, CI uses {NODE_MAJOR}", f"brew install node@{NODE_MAJOR}"
    )


def check_docker(p: Probes) -> Result:
    if not p.which("docker"):
        return Result(
            WARN, "docker", "not on PATH (only make web-visual needs it)", "install Docker Desktop"
        )
    rc, _ = p.run(["docker", "info"])
    if rc == 0:
        return Result(OK, "docker", "daemon running")
    return Result(
        WARN, "docker", "daemon not running (only make web-visual needs it)", "open -a Docker"
    )


def check_gh(p: Probes) -> Result:
    if not p.which("gh"):
        return Result(FAIL, "gh", "not on PATH", "brew install gh && gh auth login")
    rc, _ = p.run(["gh", "auth", "status"])
    if rc == 0:
        return Result(OK, "gh", "authenticated")
    return Result(FAIL, "gh", "not authenticated", "gh auth login")


def check_venv(p: Probes) -> list[Result]:
    py = p.repo / ".venv" / "bin" / "python"
    if not (py.exists() or py.is_symlink()):
        return [Result(FAIL, "venv", ".venv missing", "make install (needs uv)")]
    out: list[Result] = []
    _, ver = p.run([str(py), "-c", "import sys;print('%d.%d' % sys.version_info[:2])"])
    if ver == CI_PYTHON:
        out.append(Result(OK, "python", f"{ver} (matches CI)"))
    else:
        out.append(
            Result(
                WARN,
                "python",
                f"venv is {ver or 'unknown'}, CI is {CI_PYTHON}",
                f"rm -rf .venv && uv python install {CI_PYTHON} && make install",
            )
        )
    if not p.which("uv"):
        out.append(Result(INFO, "venv vs uv.lock", "skipped: uv not installed"))
        return out
    rc, _ = p.run(["uv", "sync", "--all-packages", "--locked", "--check"], cwd=p.repo)
    if rc == 0:
        out.append(Result(OK, "venv vs uv.lock", "in sync"))
    else:
        out.append(Result(FAIL, "venv vs uv.lock", "out of sync", "make install"))
    return out


# The venv interpreter a script runs: its shebang, or the `exec` line uv writes for long paths.
_VENV_PYTHON = re.compile(r"(/[^\s\"']*/\.venv/bin/python[\w.]*)")


def _in_main(path: str, main: Path) -> bool:
    """Whether ``path`` belongs to the main checkout itself, not a worktree: under ``main``,
    not under ``.claude/worktrees/`` (Claude agent worktrees nest there) and with no ``.git``
    (a worktree's marker) between it and ``main``."""
    target = Path(path)
    if not target.is_relative_to(main) or target.is_relative_to(main / ".claude" / "worktrees"):
        return False
    return not any(
        (d / ".git").exists() for d in target.parents if d.is_relative_to(main) and d != main
    )


def check_venv_paths(p: Probes) -> Result:
    """The main checkout's venv runs the main checkout's code. Worktrees link `.venv` to it, so
    `uv sync` / `make install` in one rewrites the editable `.pth` files and the `bin/`
    shebangs to the worktree: launchd's nightly and the API then run an unmerged branch."""
    main = p.main()
    venv = main / ".venv"
    site = sorted(venv.glob("lib/python*/site-packages/_editable_impl_algotrade*.pth"))
    bad = [
        f"{pth.name} -> {line}"
        for pth in site
        for line in pth.read_text().splitlines()
        if line.strip() and not line.startswith(("import", "#")) and not _in_main(line, main)
    ]
    scripts = sorted((venv / "bin").iterdir()) if (venv / "bin").is_dir() else []
    for script in scripts:
        if script.is_symlink() or not script.is_file():
            continue
        with script.open("rb") as f:
            head = f.read(512)
        if head.startswith(b"#!"):
            found = _VENV_PYTHON.findall(head.decode(errors="replace"))
            bad += [f"bin/{script.name} -> {py}" for py in found[:1] if not _in_main(py, main)]
    if bad:
        shown = "; ".join(bad[:3]) + (f" (+{len(bad) - 3} more)" if len(bad) > 3 else "")
        return Result(
            FAIL,
            "venv paths",
            f"the shared venv points outside the main checkout {main}: {shown}"
            " (the nightly and the API run that code)",
            f"cd {main} && uv sync --all-packages --locked",
        )
    return Result(OK, "venv paths", f"editable installs and scripts point at {main}")


def _lock_versions(path: Path) -> dict[str, tuple[str, bool]]:
    pkgs = json.loads(path.read_text()).get("packages", {})
    return {k: (v.get("version", ""), bool(v.get("optional"))) for k, v in pkgs.items() if k}


def check_node_modules(p: Probes) -> Result:
    web = p.repo / "apps" / "web"
    installed, lock = web / "node_modules" / ".package-lock.json", web / "package-lock.json"
    fix = "make web-install"
    if not installed.exists():
        return Result(FAIL, "node_modules", "not installed", fix)
    try:
        want, have = _lock_versions(lock), _lock_versions(installed)
    except (OSError, ValueError):
        return Result(FAIL, "node_modules", "lockfile unreadable", fix)
    stale = [
        k for k, (v, optional) in want.items() if not optional and have.get(k, ("", 0))[0] != v
    ]
    if stale:
        return Result(
            FAIL, "node_modules", f"{len(stale)} packages differ from package-lock.json", fix
        )
    return Result(OK, "node_modules", "match package-lock.json")


def check_env(p: Probes) -> Result:
    missing = [k for k in p.required if k not in p.env_keys()]
    if missing:
        return Result(
            FAIL,
            ".env keys",
            "missing: " + ", ".join(missing),
            "cp .env.example .env  # then fill in the names above (see its comments)",
        )
    return Result(OK, ".env keys", "all required keys set (values not shown)")


def check_ibkr(p: Probes) -> Result:
    if p.port_open("127.0.0.1", 4002):
        return Result(INFO, "IB Gateway", "paper :4002 reachable")
    return Result(INFO, "IB Gateway", "paper :4002 not reachable (only IBKR tasks need it)")


def check_store(p: Probes) -> Result:
    url = urlparse(p.data_url())
    if url.scheme != "file":
        return Result(INFO, "store", f"{url.scheme}:// store, path check skipped")
    path = Path(url.netloc + url.path)
    path = path if path.is_absolute() else p.repo / path
    if path.exists():
        return Result(OK, "store", str(path))
    return Result(
        FAIL,
        "store",
        f"{path} does not exist",
        "set ALGOTRADE_DATA_URL=file:///abs/path in .env (the main checkout's var/data)",
    )


def check_web_dist(p: Probes) -> Result:
    """The API serves the built web from ``ALGOTRADE_WEB_DIST`` when set (ADR 0044) and
    refuses to start without its ``index.html``."""
    dist = p.web_dist()
    if dist is None:
        return Result(INFO, "web build", "ALGOTRADE_WEB_DIST unset: the API serves no files")
    path = dist if dist.is_absolute() else p.repo / dist
    if (path / "index.html").is_file():
        return Result(OK, "web build", "ALGOTRADE_WEB_DIST has index.html (rebuild on web changes)")
    return Result(
        FAIL,
        "web build",
        "ALGOTRADE_WEB_DIST names a directory without index.html: the API will not start",
        "make web-build  # and ALGOTRADE_WEB_DIST=var/web in .env (docs/hosting.md)",
    )


def check_api_build(p: Probes) -> Result:
    """The API keeps the code and GraphQL schema it started with, the web is read from disk on
    every request: a ``make web-build`` or a pull after the start serves a web the API cannot
    answer (2026-10-07: every Builder row empty). A warning: the site is up, but stale."""
    try:
        found = p.api_build()
    except Exception as exc:  # a missing venv must not crash the doctor
        return Result(INFO, "api build", f"not checked ({type(exc).__name__})")
    if found is None:
        return Result(INFO, "api build", f"no API answering at {API_URL}")
    if not found:
        return Result(OK, "api build", "the running API matches its checkout and the served web")
    return Result(WARN, "api build", "; ".join(found), "the restart or rebuild named above")


def check_llm(p: Probes) -> Result:
    """``config/site/llm.toml`` of the main checkout (the API's): one that does not load does not
    stop the API (drafting is off with this message), so it is a warning, not a failure."""
    error = p.llm_error(p.main())
    if error is None:
        return Result(OK, "llm.toml", "loads (natural-language drafts, ADR 0041)")
    return Result(
        WARN,
        "llm.toml",
        f"{error}: the API starts with drafting off and answers 503 with this message",
        "edit config/site/llm.local.toml (git-ignored) in the main checkout, then restart the API",
    )


def llm_error(main: Path) -> str | None:
    """What stops ``main``'s ``config/site/llm.toml`` loading, or ``None`` (no file loads)."""
    from algotrade.config.site.llm import LlmSettings  # noqa: PLC0415 (venv may lack it)
    from algotrade.core.model.errors import ConfigurationError  # noqa: PLC0415
    from algotrade.storage.configs.files import FileConfigStore  # noqa: PLC0415

    try:  # llm.toml with this machine's llm.local.toml over it, as the API loads it
        document = FileConfigStore(main / "config").load("site", "settings", "llm")
        LlmSettings.from_document(document)
    except ConfigurationError as exc:
        return str(exc)
    return None


# The launchd agents (``algotrade-ingest schedule``, ``algotrade-api schedule``): label -> the
# command that rewrites it. Each must run the main checkout's code from the main checkout.
AGENTS = {
    "com.algotrade.nightly": ".venv/bin/algotrade-ingest schedule",
    "com.algotrade.api": ".venv/bin/algotrade-api schedule",
}


def check_agents(p: Probes) -> list[Result]:
    """Each installed launchd agent runs this (main) checkout's venv in this checkout: an agent
    written in a worktree or another clone serves or ingests with code nobody reviewed here."""
    main = p.main()
    out = []
    for label, rewrite in AGENTS.items():
        installed = p.launch_agents / f"{label}.plist"
        if not installed.exists():
            out.append(Result(INFO, label, "not installed"))
            continue
        try:
            agent = plistlib.loads(installed.read_bytes())
            paths = [str(agent["ProgramArguments"][0]), str(agent["WorkingDirectory"])]
        except (OSError, ValueError, LookupError, TypeError, plistlib.InvalidFileException):
            paths = []
        bad = [x for x in paths if not _in_main(x, main)]
        if paths and not bad and Path(paths[0]).exists():
            out.append(Result(OK, label, f"installed, runs {main}"))
            continue
        shown = ", ".join(bad) if bad else "an unreadable plist or a missing program"
        out.append(
            Result(
                FAIL,
                label,
                f"the installed agent does not run the main checkout {main}: {shown}",
                f"cd {main} && {rewrite}  # then run the install commands it prints",
            )
        )
    return out


def check_disk(p: Probes) -> Result:
    free = p.free_bytes(p.main()) / 1e9
    if free >= LOW_DISK_GB:
        return Result(OK, "disk", f"{free:.0f} GB free")
    return Result(
        WARN,
        "disk",
        f"{free:.1f} GB free, under {LOW_DISK_GB} GB (a full disk stops agents and the nightly)",
        f"{p.repo}/scripts/worktree.sh --prune-merged  # then rm -rf the caches it did not cover",
    )


def check_worktrees(p: Probes) -> Result:
    """Leftover worktrees of merged PRs (same detection as ``worktree.sh --prune-merged``)."""
    script = p.repo / "scripts" / "worktree.sh"
    rc, out = p.run(["bash", str(script), "--prune-merged", "--dry-run"], cwd=p.main())
    if rc != 0:
        return Result(INFO, "worktrees", "merged-PR worktree check skipped (needs gh)")
    merged = [x for x in out.splitlines() if x.startswith("would remove /")]
    if len(merged) <= MAX_MERGED_WORKTREES:
        return Result(OK, "worktrees", f"{len(merged)} of merged PRs (each holds ~440 MB)")
    return Result(
        WARN,
        "worktrees",
        f"{len(merged)} worktrees of merged PRs, over {MAX_MERGED_WORKTREES}"
        " (each holds its own node_modules, ~440 MB)",
        f"{script} --prune-merged",
    )


def _last_blocked(main: Path) -> str:
    """The last BLOCKED line of the deploy log, as ``; last: <line>`` (empty when none)."""
    try:
        lines = (main / "var" / "logs" / "deploy.log").read_text().splitlines()
    except OSError:
        return ""
    blocked = [x for x in lines if "BLOCKED" in x]
    return f"; last: {blocked[-1]}" if blocked else ""


def check_main_checkout(p: Probes) -> list[Result]:
    """The main checkout is what the API and the nightly run: it belongs on ``main`` at
    ``origin/main`` (`scripts/ops/deploy.sh` moves it), and its committed site config is clean
    (a machine's own values go in the git-ignored ``config/site/<name>.local.toml``)."""
    main = p.main()
    git = ["git", "-C", str(main)]
    _, branch = p.run([*git, "rev-parse", "--abbrev-ref", "HEAD"])
    _, head = p.run([*git, "rev-parse", "HEAD"])
    rc, origin = p.run([*git, "rev-parse", "origin/main"])
    out = []
    if branch != "main":
        out.append(
            Result(
                WARN,
                "main checkout",
                f"on {branch or 'an unknown branch'}, not main (the API and the nightly run it; "
                "deploy.sh refuses while it is off main, so auto-deploy is blocked)"
                + _last_blocked(main),
                f"cd {main} && git switch main",
            )
        )
    elif rc == 0 and head != origin:
        out.append(
            Result(
                WARN,
                "main checkout",
                "main is not at origin/main (behind, ahead or not fetched)",
                f"{main}/scripts/ops/deploy.sh  # or git pull --ff-only origin main",
            )
        )
    else:
        out.append(Result(OK, "main checkout", "on main at origin/main"))
    _, dirty = p.run([*git, "status", "--porcelain", "--", "config/site"])
    if dirty:
        files = ", ".join(x.split()[-1] for x in dirty.splitlines()[:3])
        out.append(
            Result(
                WARN,
                "site config",
                f"uncommitted changes in the main checkout's config/site: {files}",
                "move this machine's values to config/site/<name>.local.toml (git-ignored), "
                "then git restore the committed file (docs/configuration.md)",
            )
        )
    return out


def check_running_checks(p: Probes) -> Result:
    """Other `make check` runs on this machine (each takes 30-40 min; two at once time out)."""
    rc, out = p.run(["pgrep", "-f", "check_lock.sh"])  # once per run, not make + make check-gates
    pids = [x for x in out.split() if rc == 0 and x.isdigit() and int(x) != os.getpid()]
    if not pids:
        return Result(OK, "make check", "no other run in progress")
    where = []
    for pid in pids:
        _, lsof = p.run(["lsof", "-a", "-p", pid, "-d", "cwd", "-Fn"])
        cwd = next((x[1:] for x in lsof.splitlines() if x.startswith("n")), "?")
        where.append(f"{pid} in {cwd}")
    return Result(
        INFO,
        "make check",
        f"{len(pids)} other run(s): "
        + "; ".join(where)
        + " (stop your own by its PID, never pkill)",
    )


def run_checks(p: Probes) -> list[Result]:
    return [
        check_uv(p),
        check_node(p),
        check_docker(p),
        check_gh(p),
        *check_venv(p),
        check_venv_paths(p),
        check_node_modules(p),
        check_disk(p),
        check_worktrees(p),
        check_env(p),
        check_ibkr(p),
        check_store(p),
        check_web_dist(p),
        check_api_build(p),
        check_llm(p),
        *check_main_checkout(p),
        check_running_checks(p),
        *check_agents(p),
    ]


def render(results: list[Result]) -> tuple[str, int]:
    lines = []
    for r in results:
        lines.append(f"[{r.level:>4}] {r.name}: {r.detail}")
        if r.level in (FAIL, WARN) and r.fix:
            lines.append(f"       fix: {r.fix}")
    failed = sum(r.level == FAIL for r in results)
    lines.append(f"{failed} hard failure(s)" if failed else "ready")
    return "\n".join(lines), 1 if failed else 0


def main() -> int:
    try:
        from algotrade.config.env import (  # noqa: PLC0415 (venv may lack it)
            REQUIRED_KEYS,
            data_url,
            dotenv_keys,
            load_dotenv,
            web_dist,
        )
    except ImportError:  # no usable venv: still report everything that does not need the library
        probes = Probes()
        extra = [Result(FAIL, "library", "algotrade not importable", "make install (needs uv)")]
    else:
        load_dotenv(REPO / ".env")  # as the API and the nightly see it (never printed)
        probes = Probes(
            env_keys=lambda: dotenv_keys(REPO / ".env"),
            data_url=data_url,
            required=REQUIRED_KEYS,
            web_dist=web_dist,
            llm_error=llm_error,
        )
        extra = []
    text, code = render(run_checks(probes) + extra)
    sys.stdout.write(text + "\n")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
