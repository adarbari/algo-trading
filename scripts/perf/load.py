"""`make load`: replay every page's GraphQL mix against a running API from many virtual users.

By hand on an idle machine (never in CI). Each virtual user loads one page at a time = the
page's operations in parallel, like the browser; its page time is the slowest operation. Per
page and concurrency level it reports p50 / p95 / p99 page time and the error and 503 rate,
and for the API process (by `--pid`, or found by port with `lsof`) the peak RSS and mean CPU
sampled with `ps`. The operation documents are parsed from the web's generated
`gql.ts` (so the mix is the one the browser sends); the variables per page are `PAGES` below.
Start an API on a spare port first: `ALGOTRADE_AUTH=off .venv/bin/algotrade-api --port 8011`.

Every page load also sends the shell's operations (`SHELL`: Viewer, StatusStrip, Regime, as the
browser's top bar does). A 503 is retried like the web client (`Retry-After` x (1 + attempt / 2)
x U(0.5, 1.5), up to 5 retries); 503s seen and errors after retries are reported apart, with the
errors counted by cause (HTTP status, exception class, first GraphQL error message).

Scenarios: `warm` (one warming pass, then the measured run), `cold` (the operator restarts
the API right before; the first pass is measured as is), `first-visit` (a fresh client per
page load, no cookies or cache; server-side the same as warm for now), `stress` (= warm, no
think time) and `realistic` (warm; each virtual user waits an exponential think time, mean
`--think` 10 s, between page loads; /health is polled and the run ends PASS or FAIL against
`CRITERIA`). The load client's own CPU is reported per level.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import random
import re
import subprocess
import sys
import threading
import time
from collections import Counter, defaultdict
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
SCENARIOS = ("warm", "cold", "first-visit", "stress", "realistic")
KEEPALIVE_EXPIRY = 4.0  # seconds: below uvicorn's 5 s idle close, so no reused dead connection
BUSY_RETRIES = 5  # as apps/web/src/shared/api/graphql.ts
CRITERIA = {  # the realistic scenario's pass line
    "page_p95_s": 2.5,
    "error_rate": 0.005,
    "peak_rss_mb": 2048.0,
    "health_p99_s": 0.25,
}
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
    "ideas": [Op("IdeasPage", _static(limit=200, names=IDEA_NAMES))],
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

# The shell every page sends (apps/web WorkspaceLayout: useViewer, SystemStatusStrip, RegimeChip).
SHELL = [Op("Viewer", _static()), Op("StatusStrip", _static(admin=True)), Op("Regime", _static())]


def page_ops(page: str) -> list[Op]:
    """The shell's operations plus the page's own, one of each name (the browser caches by key)."""
    ops = {op.name: op for op in SHELL}
    ops.update({op.name: op for op in PAGES[page]})
    return list(ops.values())


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
    errors: int = 0  # operations still failed after the retries
    unavailable: int = 0  # HTTP 503 responses seen (before any retry succeeded)
    causes: list[str] = field(default_factory=list)  # one per failed operation


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
            "causes": dict(Counter(c for i in items for c in i.causes)),
        }
    return rows


def render_table(report: dict) -> str:
    """The printable table of a report: one block per concurrency level."""
    lines = [f"scenario {report['scenario']}, {report['seconds']}s per level, {report['url']}"]
    for level in report["levels"]:
        res = level["resources"]
        lines.append(
            f"\n{level['users']} users: {level['loads']} page loads, "
            f"peak RSS {res['peak_rss_mb']:.0f} MB, mean CPU {res['mean_cpu_pct']:.0f}%, "
            f"load client CPU {level.get('client_cpu_pct', 0.0):.0f}%, "
            f"/health p99 {level.get('health', {}).get('p99', 0.0) * 1000:.0f} ms"
        )
        lines.append(
            f"{'page':<17}{'loads':>7}{'p50 s':>8}{'p95 s':>8}{'p99 s':>8}{'err %':>7}{'503 %':>7}"
        )
        for page, r in level["pages"].items():
            lines.append(
                f"{page:<17}{r['loads']:>7}{r['p50']:>8.2f}{r['p95']:>8.2f}{r['p99']:>8.2f}"
                f"{r['error_rate'] * 100:>7.1f}{r['rate_503'] * 100:>7.1f}"
            )
        causes: Counter = Counter()
        for r in level["pages"].values():
            causes.update(r.get("causes", {}))
        for cause, n in causes.most_common():
            lines.append(f"  errors after retries: {n} x {cause}")
        if "pass" in level:
            lines.append(f"{'PASS' if level['pass'] else 'FAIL'} ({level['users']} users)")
            lines.extend(level["checks"])
    return "\n".join(lines)


def _client(url: str, users: int):
    limits = httpx.Limits(
        max_connections=users * 8,
        max_keepalive_connections=users * 8,
        keepalive_expiry=KEEPALIVE_EXPIRY,
    )
    return httpx.AsyncClient(base_url=url, limits=limits, timeout=REQUEST_TIMEOUT)


def busy_delay(retry_after: str | None, attempt: int, rand: float) -> float:
    """Seconds to wait before retry `attempt` (0-based): the web client's `busyDelayMs`;
    `rand` is a uniform draw in [0, 1)."""
    try:
        base = float(retry_after) if retry_after else 0.0
    except ValueError:
        base = 0.0
    return (base or 1.0) * (1 + attempt / 2) * (0.5 + rand)


def think_time(mean: float, rng: random.Random) -> float:
    """An exponential think time with the given mean (0 for a mean of 0)."""
    return rng.expovariate(1 / mean) if mean > 0 else 0.0


@dataclass
class OpResult:
    """One operation after its retries: whether it failed, the 503s seen, and why it failed."""

    failed: bool = False
    seen_503: int = 0
    cause: str | None = None


def response_cause(status: int, body: object) -> str | None:
    """Why a response is a failure: `HTTP <status>`, `GraphQL: <first message>`, or None."""
    if status != 200:
        return f"HTTP {status}"
    errors = body.get("errors") if isinstance(body, dict) else None
    if errors:
        first = errors[0] if isinstance(errors, list) else errors
        message = first.get("message") if isinstance(first, dict) else first
        return f"GraphQL: {str(message)[:80]}"
    return None


async def _op(client, docs: dict[str, str], op: Op, session: date, sleep=asyncio.sleep) -> OpResult:
    """Send one operation, retrying a 503 like the web client; the result after the retries."""
    payload = {"query": docs[op.name], "variables": op.variables(session)}
    out = OpResult()
    for attempt in range(BUSY_RETRIES + 1):
        try:
            r = await client.post("/graphql", json=payload)
        except Exception as exc:
            out.failed, out.cause = True, f"exception {type(exc).__name__}"
            return out
        if r.status_code == 503:
            out.seen_503 += 1
            if attempt < BUSY_RETRIES:
                await sleep(busy_delay(r.headers.get("retry-after"), attempt, random.random()))
                continue
        try:
            body = r.json()
        except ValueError:
            body = None
        cause = response_cause(r.status_code, body)
        if cause is None and body is None:
            cause = "invalid JSON"
        out.failed, out.cause = cause is not None, cause
        return out
    return out


async def load_page(client, docs: dict[str, str], page: str, session: date) -> PageLoad:
    """One page load: the shell's and the page's operations in parallel; the time is the
    slowest of them (retries included)."""
    start = time.perf_counter()
    ends: list[float] = []

    async def timed(op: Op) -> OpResult:
        got = await _op(client, docs, op, session)
        ends.append(time.perf_counter() - start)
        return got

    results = await asyncio.gather(*(timed(op) for op in page_ops(page)))
    return PageLoad(
        page,
        max(ends),
        sum(1 for r in results if r.failed),
        sum(r.seen_503 for r in results),
        [r.cause or "unknown" for r in results if r.failed],
    )


async def poll_health(url: str, stop: asyncio.Event, into: list[float], every: float = 1.0) -> None:
    """Time `GET /health` once per `every` seconds until `stop`; a failure counts as 10 s."""
    async with httpx.AsyncClient(base_url=url, timeout=10.0) as c:
        while not stop.is_set():
            t = time.perf_counter()
            try:
                await c.get("/health")
                into.append(time.perf_counter() - t)
            except Exception:
                into.append(10.0)
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), every)


def verdict(level: dict) -> tuple[bool, list[str]]:
    """PASS / FAIL of one level against `CRITERIA`, with a line per check."""
    pages = list(level["pages"].values())
    loads = sum(p["loads"] for p in pages) or 1
    failed = sum(p["error_rate"] * p["loads"] for p in pages) / loads
    checks = [
        ("page p95", max((p["p95"] for p in pages), default=0.0), CRITERIA["page_p95_s"], "s"),
        ("errors after retries", failed, CRITERIA["error_rate"], ""),
        ("API peak RSS", level["resources"]["peak_rss_mb"], CRITERIA["peak_rss_mb"], " MB"),
        ("/health p99", level["health"]["p99"], CRITERIA["health_p99_s"], "s"),
    ]
    lines, ok = [], True
    for name, value, limit, unit in checks:
        good = value <= limit
        ok = ok and good
        mark = "ok  " if good else "FAIL"
        lines.append(f"  {mark} {name}: {value:.3g}{unit} (limit {limit:g}{unit})")
    return ok, lines


async def run_level(
    url, docs, session, users, seconds, fresh_client, think: float = 0.0, rng=None
) -> list[PageLoad]:
    """`users` virtual users loading pages in rotation (each starts on a different page); with
    a `think` mean each waits an exponential think time before every load (the first too)."""
    rng = rng or random.Random()
    names = list(PAGES)
    deadline = time.monotonic() + seconds
    loads: list[PageLoad] = []
    shared = None if fresh_client else _client(url, users)

    async def user(i: int) -> None:
        k = i
        while time.monotonic() < deadline:
            if think:
                wait = min(think_time(think, rng), max(0.0, deadline - time.monotonic()))
                await asyncio.sleep(wait)
                if time.monotonic() >= deadline:
                    break
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
    missing = {op.name for p in PAGES for op in page_ops(p)} - set(docs)
    if missing:
        sys.exit(f"operations not in gql.ts: {sorted(missing)}")
    session = await resolve_session(args.url)
    fresh = args.scenario == "first-visit"
    if args.scenario in ("warm", "stress", "realistic"):
        async with _client(args.url, 1) as c:
            await asyncio.gather(*(load_page(c, docs, p, session) for p in PAGES))
    levels = []
    for users in args.users:
        sample, stop = Sample(), threading.Event()
        thread = threading.Thread(target=sample_process, args=(pid, stop, sample)) if pid else None
        if thread:
            thread.start()
        think = args.think if args.scenario == "realistic" else 0.0
        health: list[float] = []
        health_stop = asyncio.Event()
        poller = asyncio.create_task(poll_health(args.url, health_stop, health))
        cpu0, wall0 = time.process_time(), time.perf_counter()
        loads = await run_level(args.url, docs, session, users, args.seconds, fresh, think)
        client_cpu = (time.process_time() - cpu0) / max(time.perf_counter() - wall0, 1e-9) * 100
        health_stop.set()
        await poller
        stop.set()
        if thread:
            thread.join()
        level = {
            "users": users,
            "loads": len(loads),
            "pages": summarise(loads),
            "client_cpu_pct": client_cpu,
            "health": {"polls": len(health), "p99": percentile(health, 99)},
            "resources": {
                "peak_rss_mb": max(sample.rss_mb, default=0.0),
                "mean_cpu_pct": sum(sample.cpu) / len(sample.cpu) if sample.cpu else 0.0,
            },
        }
        if args.scenario == "realistic":
            level["pass"], level["checks"] = verdict(level)
        levels.append(level)
    return {
        "when": datetime.now(UTC).isoformat(),
        "url": args.url,
        "scenario": args.scenario,
        "seconds": args.seconds,
        "think_mean_s": args.think,
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
    p.add_argument("--think", type=float, default=10.0, help="realistic: mean think time, s")
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
