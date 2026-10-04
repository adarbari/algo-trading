"""`make doctor`: is this machine ready to work in the repo? Prints one line per check and the
exact fix command for each failure. Exits non-zero only on hard failures (warnings and info
never fail it). Every probe goes through `Probes`, so tests pass fakes. Never prints .env values.
"""

from __future__ import annotations

import json
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


def _run(cmd: list[str], cwd: Path | None = None) -> tuple[int, str]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, check=False, cwd=cwd, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 127, str(exc)
    return p.returncode, (p.stdout + p.stderr).strip()


def _port_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.5):
            return True
    except OSError:
        return False


@dataclass
class Probes:
    """The machine, as the checks see it. Defaults are real; tests override."""

    repo: Path = REPO
    which: Callable[[str], str | None] = shutil.which
    run: Callable[..., tuple[int, str]] = _run
    port_open: Callable[[str, int], bool] = _port_open
    env_keys: Callable[[], set[str]] = field(default=set)
    data_url: Callable[[], str] = field(default=lambda: "file://./var/data")
    required: tuple[str, ...] = ()


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


def run_checks(p: Probes) -> list[Result]:
    return [
        check_uv(p),
        check_node(p),
        check_docker(p),
        check_gh(p),
        *check_venv(p),
        check_node_modules(p),
        check_env(p),
        check_ibkr(p),
        check_store(p),
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
        )
    except ImportError:  # no usable venv: still report everything that does not need the library
        probes = Probes()
        extra = [Result(FAIL, "library", "algotrade not importable", "make install (needs uv)")]
    else:
        probes = Probes(
            env_keys=lambda: dotenv_keys(REPO / ".env"), data_url=data_url, required=REQUIRED_KEYS
        )
        extra = []
    text, code = render(run_checks(probes) + extra)
    sys.stdout.write(text + "\n")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
