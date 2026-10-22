"""`make api-latency-views-capture`: the exhaustive, per-VIEW capture of what the web sends.

This script STARTS both servers itself, so the browser can only ever reach a clone: an API on a
spare loopback port serving `--data-url` (the same starter as `api_latency.py`, text model off,
caches off, warmer off), then a Vite dev server on another spare port whose `API_PROXY_TARGET` is
THAT API (Vite's default target is the live API on :8000, which nothing here may reach). Before
anything starts it refuses (exit 2) unless `--data-url` names a clone (`check_target`, never
confirmed) and the bounds are sane; it refuses a port of 8000 or a non-loopback host. The
crawler (`capture_views.mjs`) additionally aborts every browser request that leaves the web
origin or writes (see `view_crawler.mjs`). It fills `benchmarks/api_latency_views.json` view by
view (resumable: captured views are skipped; `--retry` revisits the ones that timed out),
at most `--max-views` per run; then `view_coverage.py` writes docs/perf/view-coverage.md.
"""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
import api_latency as al
import views as v

REPO = Path(__file__).resolve().parents[2]
WEB = REPO / "apps" / "web"
CRAWLER = Path(__file__).resolve().parent / "capture_views.mjs"
LOOPBACK = {"127.0.0.1", "localhost", "::1", "[::1]"}
LIVE_PORTS = {8000}  # the launchd API (and Vite's default proxy target)
MAX_VIEWS_CAP = 200


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    p.add_argument("--data-url", help="file:// URL of the CLONE to serve (required)")
    p.add_argument("--max-views", type=int, default=20, help="views visited this run")
    p.add_argument(
        "--only-route",
        metavar="PATTERN",
        help="only views of this route: `/edges` (and `/edges/...`), or a glob `/guide/*`",
    )
    p.add_argument("--view-timeout", type=int, default=60, help="seconds per view")
    p.add_argument("--depth", type=int, default=2, help="clicks deep the crawler discovers")
    p.add_argument("--max-controls", type=int, default=40, help="controls discovered per view")
    p.add_argument("--retry", action="store_true", help="revisit skipped / timed-out views")
    p.add_argument("--views-file", default=str(v.VIEWS_FILE))
    return p.parse_args(argv)


def check_crawl(args: argparse.Namespace, stores: list[Path], web: Path | None = None) -> str:
    """The clone's ``file://`` URL, or an ``al.RefusalError``: no ``--data-url``, the real
    store (or inside / around it), or a bound out of range."""
    if not args.data_url:
        raise al.RefusalError(
            "the crawler needs --data-url (a CLONE of the store); it never runs against the "
            "real store"
        )
    checked = al.check_target(args.data_url, stores, False, need_url=True)
    assert checked is not None
    if not 1 <= args.max_views <= MAX_VIEWS_CAP:
        raise al.RefusalError(f"--max-views must be 1..{MAX_VIEWS_CAP}")
    if args.view_timeout < 5 or args.depth < 0 or args.max_controls < 0:
        raise al.RefusalError("--view-timeout must be >= 5 s, --depth and --max-controls >= 0")
    web = web or WEB
    if not (web / "node_modules").is_dir():
        raise al.RefusalError(f"{web}/node_modules is missing: run `npm ci` there (Vite needs it)")
    if not Path(args.views_file).is_file():
        raise al.RefusalError(f"{args.views_file} does not exist: run view_coverage.py first")
    return checked


def check_local(url: str) -> str:
    """``url`` when it is a loopback server that is not the live API's port."""
    parsed = urlparse(url)
    if (parsed.hostname or "") not in LOOPBACK:
        raise al.RefusalError(f"{url}: only a loopback server")
    if parsed.port is None or parsed.port in LIVE_PORTS:
        raise al.RefusalError(f"{url}: port {parsed.port} is the live API's or unset")
    return url


def wait_for(url: str, seconds: float = 90) -> None:
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        try:
            with urllib.request.urlopen(url, timeout=3) as r:
                if r.status == 200:
                    return
        except OSError:
            time.sleep(0.5)
    raise RuntimeError(f"{url} did not come up")


def vite_command(port: int) -> list[str]:
    return ["npx", "vite", "--host", "127.0.0.1", "--port", str(port)]


def vite_env(api_url: str, base: dict[str, str]) -> dict[str, str]:
    """The dev server's environment: its proxy points at OUR API, never Vite's default."""
    return {**base, "API_PROXY_TARGET": check_local(api_url)}


def start_servers(data_url: str, api_factory=al.Api, popen=subprocess.Popen):  # type: ignore[no-untyped-def]
    """(api, vite process, web url): the clone's API and a Vite proxying to it, both loopback."""
    api = api_factory("uncached", data_url=data_url)
    try:
        check_local(api.url)
        port = al.free_port()
        web_url = check_local(f"http://127.0.0.1:{port}")
        vite = popen(
            vite_command(port),
            cwd=WEB,
            env=vite_env(api.url, dict(os.environ)),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,  # its own process group: npx's child dies with it
        )
    except BaseException:
        api.close()
        raise
    return api, vite, web_url


def stop_group(proc, killpg=os.killpg) -> None:  # type: ignore[no-untyped-def]
    """Stop a server and what it spawned (npx -> vite): SIGTERM its group, SIGKILL after 15 s.
    Where the group cannot be signalled (PermissionError) the process itself is terminated; and
    once the leader is gone the group is probed (signal 0) and killed if a child survived."""
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            killpg(proc.pid, sig)
        except ProcessLookupError:
            return
        except PermissionError:
            (proc.terminate if sig == signal.SIGTERM else proc.kill)()
        try:
            proc.wait(timeout=15)
            break
        except subprocess.TimeoutExpired:
            continue
    try:
        killpg(proc.pid, 0)  # the leader is gone: is anything of its group left?
        killpg(proc.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        return


def install_stop_handlers() -> None:
    """A stopped run (SIGTERM / SIGHUP) unwinds through the `finally` that stops the servers."""
    for sig in (signal.SIGTERM, signal.SIGHUP):
        signal.signal(sig, lambda *_: sys.exit(143))


def stop_all(api, vite, stop=stop_group) -> None:  # type: ignore[no-untyped-def]
    """Stop every server, each in its own try/finally: the API first (the memory hog), then Vite;
    one failing stop never skips the other. Further SIGTERM / SIGHUP are ignored meanwhile: a
    second one would raise inside the stop and leave a server running."""
    for sig in (signal.SIGTERM, signal.SIGHUP):
        signal.signal(sig, signal.SIG_IGN)
    try:
        api.close()
    finally:
        stop(vite)


def node_command(args: argparse.Namespace, api_url: str, web_url: str) -> list[str]:
    """The crawler's command line."""
    cmd = [
        "node",
        str(CRAWLER),
        "--api-url", api_url,
        "--web-url", web_url,
        "--views-file", args.views_file,
        "--max-views", str(args.max_views),
        "--view-timeout", str(args.view_timeout),
        "--depth", str(args.depth),
        "--max-controls", str(args.max_controls),
        "--retry", "true" if args.retry else "false",
    ]  # fmt: skip
    if args.only_route:
        cmd += ["--only-route", args.only_route]
    return cmd


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        data_url = check_crawl(
            args, al.real_stores(dict(os.environ), REPO, al.main_checkout_of(REPO))
        )
    except al.RefusalError as err:
        print(f"refused: {err}", file=sys.stderr)
        return 2
    install_stop_handlers()  # BEFORE the servers: the API takes up to 90 s to start
    api, vite, web_url = start_servers(data_url)
    try:
        wait_for(f"{web_url}/api/health")  # through Vite's proxy: it reaches our API
        return subprocess.run(
            node_command(args, api.url, web_url), cwd=REPO, check=False
        ).returncode
    finally:
        stop_all(api, vite)


if __name__ == "__main__":
    raise SystemExit(main())
