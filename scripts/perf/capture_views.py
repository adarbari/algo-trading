"""`make api-latency-views-capture`: the exhaustive, per-VIEW capture of what the web sends.

Starts `capture_views.mjs` (Playwright, one browser context) against an API you started on a
CLONE of the store and a web server proxying to it; this script starts neither. Before anything
runs it refuses (exit 2) unless `--data-url` names a clone (the same real-store guard as
`api_latency.py --uncached`: `check_target`, never confirmed), both URLs are local, and the
bounds are sane. The crawler fills `benchmarks/api_latency_views.json` view by view (resumable:
captured views are skipped; `--retry` revisits the ones that timed out or were missing),
at most `--max-views` per run; then `view_coverage.py` writes docs/perf/view-coverage.md.

The clone the API serves is attested by `--data-url`, which this script cannot verify against
the running API: start the API with `ALGOTRADE_DATA_URL` set to the same clone.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
import api_latency as al
import views as v

REPO = Path(__file__).resolve().parents[2]
CRAWLER = Path(__file__).resolve().parent / "capture_views.mjs"
LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1", "[::1]"}
MAX_VIEWS_CAP = 200


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    p.add_argument("--api-url", required=True, help="the API serving the clone (local)")
    p.add_argument("--web-url", required=True, help="the web server proxying to it (local)")
    p.add_argument("--data-url", help="file:// URL of the CLONE the API serves (required)")
    p.add_argument("--max-views", type=int, default=20, help="views visited this run")
    p.add_argument("--only-route", metavar="PATTERN", help="only views of this route, e.g. /edges")
    p.add_argument("--view-timeout", type=int, default=60, help="seconds per view")
    p.add_argument("--depth", type=int, default=2, help="clicks deep the crawler discovers")
    p.add_argument("--retry", action="store_true", help="revisit skipped / timed-out views")
    p.add_argument("--views-file", default=str(v.VIEWS_FILE))
    return p.parse_args(argv)


def check_crawl(args: argparse.Namespace, stores: list[Path]) -> str:
    """The clone's ``file://`` URL, or an ``al.RefusalError``: no ``--data-url``, the real
    store (or inside / around it), a non-local URL, or a bound out of range."""
    if not args.data_url:
        raise al.RefusalError(
            "the crawler needs --data-url (a CLONE of the store the API serves); it never "
            "runs against the real store"
        )
    checked = al.check_target(args.data_url, stores, False, need_url=True)
    assert checked is not None
    for name, url in (("--api-url", args.api_url), ("--web-url", args.web_url)):
        host = urlparse(url).hostname or ""
        if host not in LOCAL_HOSTS:
            raise al.RefusalError(f"{name} {url}: only a local server (127.0.0.1 / localhost)")
    if not 1 <= args.max_views <= MAX_VIEWS_CAP:
        raise al.RefusalError(f"--max-views must be 1..{MAX_VIEWS_CAP}")
    if args.view_timeout < 5 or args.depth < 0:
        raise al.RefusalError("--view-timeout must be >= 5 s and --depth >= 0")
    if not Path(args.views_file).is_file():
        raise al.RefusalError(f"{args.views_file} does not exist: run view_coverage.py first")
    return checked


def node_command(args: argparse.Namespace) -> list[str]:
    """The crawler's command line."""
    cmd = [
        "node",
        str(CRAWLER),
        "--api-url", args.api_url,
        "--web-url", args.web_url,
        "--views-file", args.views_file,
        "--max-views", str(args.max_views),
        "--view-timeout", str(args.view_timeout),
        "--depth", str(args.depth),
        "--retry", "true" if args.retry else "false",
    ]  # fmt: skip
    if args.only_route:
        cmd += ["--only-route", args.only_route]
    return cmd


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        check_crawl(args, al.real_stores(dict(os.environ), REPO, al.main_checkout_of(REPO)))
    except al.RefusalError as err:
        print(f"refused: {err}", file=sys.stderr)
        return 2
    return subprocess.run(node_command(args), cwd=REPO, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
