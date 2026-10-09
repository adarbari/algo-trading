"""`make load`: replay every page's GraphQL mix against a running API from many virtual users.

By hand on an idle machine (never in CI). Each virtual user loads one page at a time = the
page's operations in parallel, like the browser; its page time is the slowest operation. Per
page and concurrency level it reports p50 / p95 / p99 page time and the error and 503 rate,
and for the API process (by `--pid`, or found by port with `lsof`) the peak RSS and mean CPU
sampled with `ps`. The operation documents are parsed from the web's generated
`gql.ts` (so the mix is the one the browser sends); the variables per page are `PAGES` below.
Start an API on a spare port first: `ALGOTRADE_AUTH=off .venv/bin/algotrade-api --port 8011`.

Scenarios: `warm` (one warming pass, then the measured run), `cold` (the operator restarts
the API right before; the first pass is measured as is) and `first-visit` (a fresh client per
page load, no cookies or cache; server-side the same as warm for now).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import subprocess
import sys
import threading
import time
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import httpx2 as httpx  # the httpx API; installed with the test dependencies

REPO = Path(__file__).resolve().parents[2]
GQL_TS = REPO / "apps/web/src/shared/api/generated/graphql/gql.ts"
OUT_DIR = REPO / "var/perf"
REQUEST_TIMEOUT = (
    30.0  # seconds: a slower operation counts as an error (the page is unusable by then)
)
SCENARIOS = ("warm", "cold", "first-visit")
IDEA_NAMES = [
    "rollup.earnings@v1.next_earnings_date",
    "rollup.earnings@v1.last_earnings_date",
    "rollup.earnings@v1.days_to_earnings",
    "rollup.nearest_expiry@v1.dte",
    "feature.earnings_before_expiry",
    "feature.vrp_iv30",
    "rollup.price_stats@v2.close",
    "rollup.trend_stats@v2.ret_1d",
    "rollup.relative_strength@v1.sector_etf",
]
REGIME_NAMES = [
    f"market.regime@v3.{n}" for n in ("macro_risk", "market_stress", "label", "market_coverage")
]


@dataclass(frozen=True)
class Op:
    """One operation of a page: the document name and the variables it is sent with."""

    name: str
    variables: Callable[[date], dict]


def _static(**variables: object) -> Callable[[date], dict]:
    return lambda _session: dict(variables)


PAGES: dict[str, list[Op]] = {
    "ideas": [
        Op("IdeasPage", _static(limit=200, names=IDEA_NAMES)),
        Op("Viewer", _static()),
        Op("StatusStrip", _static(admin=True)),
        Op("Regime", _static()),
    ],
    "regime": [
        Op("Regime", _static()),
        Op("RegimeEpisodes", _static()),
        Op("RegimeSignals", _static()),
        Op(
            "MarketHistory",
            lambda s: {
                "names": REGIME_NAMES,
                "start": "1971-01-01",
                "end": s.isoformat(),
                "points": 600,
            },
        ),
    ],
    "edges": [Op("EdgesPage", _static())],
    "screeners": [
        Op("ScreenerConfigs", _static()),
        Op("ScreenerRuns", _static()),
        Op("ScreenerTrackRecords", _static()),
    ],
    "calendar": [Op("EventCalendar", _static(instrumentIds=[], scope=True))],
    "explore-aapl": [
        Op(
            "InstrumentPrices",
            lambda s: {"key": "AAPL", "start": (s - timedelta(days=365)).isoformat()},
        ),
        Op("InstrumentEvents", _static(key="AAPL")),
        Op("InstrumentEventStudy", _static(key="AAPL")),
    ],
    "admin-ingestion": [
        Op("IngestionCompleteness", _static(sessions=10)),
        Op("NightlyRuns", _static(limit=10)),
        Op("QualityChecks", _static()),
    ],
}

_DOC = re.compile(r'^\s+("(?:[^"\\]|\\.)*"): typeof', re.M)
_HEAD = re.compile(r"\b(?:query|mutation)\s+(\w+)")


def parse_documents(ts_text: str) -> dict[str, str]:
    """Operation name -> document text, from the `Documents` map of the generated gql.ts."""
    docs: dict[str, str] = {}
    for m in _DOC.finditer(ts_text):
        text = json.loads(m.group(1))
        head = _HEAD.search(text)
        if head:
            docs[head.group(1)] = text
    return docs


def percentile(values: list[float], q: float) -> float:
    """The q-th percentile (0-100) by linear interpolation; 0.0 for no values."""
    if not values:
        return 0.0
    ordered = sorted(values)
    pos = (len(ordered) - 1) * q / 100
    lo = int(pos)
    hi = min(lo + 1, len(ordered) - 1)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (pos - lo)


@dataclass
class PageLoad:
    """One page load by one virtual user: its time (slowest operation) and how it ended."""

    page: str
    seconds: float
    errors: int = 0
    unavailable: int = 0  # HTTP 503


@dataclass
class Sample:
    """The API process's resource use over a run, sampled with `ps`."""

    rss_mb: list[float] = field(default_factory=list)
    cpu: list[float] = field(default_factory=list)


def _ps(pid: int) -> tuple[float, float] | None:
    out = subprocess.run(
        ["ps", "-o", "rss=,%cpu=", "-p", str(pid)], capture_output=True, text=True, check=False
    ).stdout.split()
    return (int(out[0]) / 1024, float(out[1])) if len(out) == 2 else None


def pid_on_port(port: int) -> int | None:
    """The PID listening on a port (`lsof`), or None."""
    out = subprocess.run(
        ["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-t"],
        capture_output=True,
        text=True,
        check=False,
    ).stdout.split()
    return int(out[0]) if out else None


def sample_process(pid: int, stop: threading.Event, into: Sample, every: float = 0.5) -> None:
    """Append RSS (MB) and CPU (%) of `pid` to `into` until `stop` is set."""
    while not stop.is_set():
        got = _ps(pid)
        if got:
            into.rss_mb.append(got[0])
            into.cpu.append(got[1])
        stop.wait(every)


def summarise(loads: list[PageLoad]) -> dict[str, dict]:
    """Per page: loads, p50 / p95 / p99 seconds, error rate and 503 rate (of loads)."""
    by_page: dict[str, list[PageLoad]] = defaultdict(list)
    for load in loads:
        by_page[load.page].append(load)
    rows = {}
    for page, items in by_page.items():
        times = [i.seconds for i in items]
        n = len(items)
        rows[page] = {
            "loads": n,
            "p50": percentile(times, 50),
            "p95": percentile(times, 95),
            "p99": percentile(times, 99),
            "error_rate": sum(1 for i in items if i.errors) / n,
            "rate_503": sum(1 for i in items if i.unavailable) / n,
        }
    return rows


def render_table(report: dict) -> str:
    """The printable table of a report: one block per concurrency level."""
    lines = [f"scenario {report['scenario']}, {report['seconds']}s per level, {report['url']}"]
    for level in report["levels"]:
        res = level["resources"]
        lines.append(
            f"\n{level['users']} users: {level['loads']} page loads, "
            f"peak RSS {res['peak_rss_mb']:.0f} MB, mean CPU {res['mean_cpu_pct']:.0f}%"
        )
        lines.append(
            f"{'page':<17}{'loads':>7}{'p50 s':>8}{'p95 s':>8}{'p99 s':>8}{'err %':>7}{'503 %':>7}"
        )
        for page, r in level["pages"].items():
            lines.append(
                f"{page:<17}{r['loads']:>7}{r['p50']:>8.2f}{r['p95']:>8.2f}{r['p99']:>8.2f}"
                f"{r['error_rate'] * 100:>7.1f}{r['rate_503'] * 100:>7.1f}"
            )
    return "\n".join(lines)


def _client(url: str, users: int):
    limits = httpx.Limits(max_connections=users * 8, max_keepalive_connections=users * 8)
    return httpx.AsyncClient(base_url=url, limits=limits, timeout=REQUEST_TIMEOUT)


async def _op(client, docs: dict[str, str], op: Op, session: date) -> tuple[bool, bool]:
    """Send one operation; (failed, was_503)."""
    try:
        r = await client.post(
            "/graphql", json={"query": docs[op.name], "variables": op.variables(session)}
        )
    except Exception:
        return True, False
    if r.status_code != 200:
        return True, r.status_code == 503
    try:
        return bool(r.json().get("errors")), False
    except ValueError:
        return True, False


async def load_page(client, docs: dict[str, str], page: str, session: date) -> PageLoad:
    """One page load: the page's operations in parallel; the time is the slowest of them."""
    start = time.perf_counter()
    ends: list[float] = []

    async def timed(op: Op) -> tuple[bool, bool]:
        got = await _op(client, docs, op, session)
        ends.append(time.perf_counter() - start)
        return got

    results = await asyncio.gather(*(timed(op) for op in PAGES[page]))
    return PageLoad(
        page, max(ends), sum(1 for f, _ in results if f), sum(1 for _, u in results if u)
    )


async def run_level(url, docs, session, users, seconds, fresh_client) -> list[PageLoad]:
    """`users` virtual users loading pages in rotation (each starts on a different page)."""
    names = list(PAGES)
    deadline = time.monotonic() + seconds
    loads: list[PageLoad] = []
    shared = None if fresh_client else _client(url, users)

    async def user(i: int) -> None:
        k = i
        while time.monotonic() < deadline:
            page = names[k % len(names)]
            k += 1
            if fresh_client:
                async with _client(url, 1) as c:
                    loads.append(await load_page(c, docs, page, session))
            else:
                loads.append(await load_page(shared, docs, page, session))

    await asyncio.gather(*(user(i) for i in range(users)))
    if shared:
        await shared.aclose()
    return loads


async def resolve_session(url: str) -> date:
    """The session date the API serves, from `{ session { date } }`."""
    async with httpx.AsyncClient(base_url=url, timeout=60.0) as c:
        r = await c.post("/graphql", json={"query": "{ session { date } }"})
        r.raise_for_status()
        return date.fromisoformat(r.json()["data"]["session"]["date"])


async def run(args: argparse.Namespace, pid: int | None) -> dict:
    """Run every concurrency level of the scenario and return the report."""
    docs = parse_documents(GQL_TS.read_text())
    missing = {op.name for ops in PAGES.values() for op in ops} - set(docs)
    if missing:
        sys.exit(f"operations not in gql.ts: {sorted(missing)}")
    session = await resolve_session(args.url)
    fresh = args.scenario == "first-visit"
    if args.scenario == "warm":
        async with _client(args.url, 1) as c:
            await asyncio.gather(*(load_page(c, docs, p, session) for p in PAGES))
    levels = []
    for users in args.users:
        sample, stop = Sample(), threading.Event()
        thread = threading.Thread(target=sample_process, args=(pid, stop, sample)) if pid else None
        if thread:
            thread.start()
        loads = await run_level(args.url, docs, session, users, args.seconds, fresh)
        stop.set()
        if thread:
            thread.join()
        levels.append(
            {
                "users": users,
                "loads": len(loads),
                "pages": summarise(loads),
                "resources": {
                    "peak_rss_mb": max(sample.rss_mb, default=0.0),
                    "mean_cpu_pct": sum(sample.cpu) / len(sample.cpu) if sample.cpu else 0.0,
                },
            }
        )
    return {
        "when": datetime.now(UTC).isoformat(),
        "url": args.url,
        "scenario": args.scenario,
        "seconds": args.seconds,
        "session": session.isoformat(),
        "pid": pid,
        "levels": levels,
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    p.add_argument("--url", default="http://127.0.0.1:8011")
    p.add_argument("--scenario", choices=SCENARIOS, default="warm")
    p.add_argument(
        "--users", type=int, nargs="+", default=[100, 200, 300], help="concurrency levels"
    )
    p.add_argument("--seconds", type=int, default=30, help="per level")
    p.add_argument("--pid", type=int, help="API process (default: the listener on the URL's port)")
    args = p.parse_args(argv)
    port = int(args.url.rsplit(":", 1)[-1].split("/")[0])
    pid = args.pid or pid_on_port(port)
    if pid is None:
        print("no API process found for the resource sample (pass --pid)", file=sys.stderr)
    report = asyncio.run(run(args, pid))
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"{datetime.now(UTC):%Y%m%dT%H%M%SZ}.json"
    out.write_text(json.dumps(report, indent=2))
    print(render_table(report))
    print(f"\nwritten {out.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
