"""`make api-latency`: per-operation latency baseline of every API call the web UI sends on load.

Replays what the browser sent (`benchmarks/api_latency_pages.json`, written by
`make api-latency-capture`: operation, variables and document per route, with real ids from the
local store) against an API this script starts ITSELF on a free port (the real local store,
`ALGOTRADE_AUTH=off`, text model off; the launchd API on :8000 is never touched).

Per operation: COLD = the first call on a freshly started process (one new process per
operation: nothing else has warmed the store handles, the schema or the page cache);
WARM = median / p95 of 10 repeat calls with the response cache on (a hit where cacheable);
NOCACHE = the same on a process whose response cache never answers (the resolver's true cost,
one discarded priming call first). Also response bytes (decoded) and the largest list returned.
Writes `benchmarks/api_latency.json` and `docs/perf/api-latency-baseline.md` (sorted by cold ms,
then per page: the sum and the critical path, the slowest operation, of its on-load operations).
By hand on an idle machine (never in CI); `--only NAME ...` measures a subset and writes nothing.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import statistics
import subprocess
import sys
import time
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

import httpx2 as httpx  # the httpx API; installed with the test dependencies

REPO = Path(__file__).resolve().parents[2]
PAGES_FILE = REPO / "benchmarks/api_latency_pages.json"
JSON_OUT = REPO / "benchmarks/api_latency.json"
DOC_OUT = REPO / "docs/perf/api-latency-baseline.md"
REPEATS = 10
TIMEOUT = 120.0
LAUNCH = (
    "import sys, uvicorn;"
    "nocache = sys.argv[2] == '1';"
    "import algotrade_api.graphql.response_cache as rc;"
    "rc.ResponseCache.get = (lambda self, key: None) if nocache else rc.ResponseCache.get;"
    "from algotrade_api.app import app;"
    "uvicorn.run(app, host='127.0.0.1', port=int(sys.argv[1]), log_level='warning')"
)


def percentile(values: list[float], q: float) -> float:
    """The q-th percentile (0-100) by linear interpolation; 0.0 for no values."""
    if not values:
        return 0.0
    ordered = sorted(values)
    pos = (len(ordered) - 1) * q / 100
    lo = int(pos)
    hi = min(lo + 1, len(ordered) - 1)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (pos - lo)


def largest_list(data: object) -> int:
    """The length of the longest list anywhere in a response (the row count, where obvious)."""
    if isinstance(data, list):
        return max([len(data), *(largest_list(x) for x in data[:50])])
    if isinstance(data, dict):
        return max([0, *(largest_list(v) for v in data.values())])
    return 0


def inventory(pages: dict[str, list[dict]]) -> tuple[dict[str, dict], dict[str, list[str]]]:
    """Operation name -> {query, variables} (first variant seen), and route -> its distinct ops."""
    ops: dict[str, dict] = {}
    by_page: dict[str, list[str]] = {}
    for route, calls in pages.items():
        names: list[str] = []
        for call in calls:
            if call["kind"] != "graphql":
                continue
            ops.setdefault(call["op"], {"query": call["query"], "variables": call["variables"]})
            if call["op"] not in names:
                names.append(call["op"])
        by_page[route] = names
    return ops, by_page


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


class Api:
    """An API process of this script's own, on a free port."""

    def __init__(self, nocache: bool) -> None:
        self.port = free_port()
        self.url = f"http://127.0.0.1:{self.port}"
        env = {
            "ALGOTRADE_AUTH": "off",
            "ALGOTRADE_LLM": "off",
            "ALGOTRADE_IBKR_PORT": "1",  # no broker: live quotes degrade, never hang
        }
        self.proc = subprocess.Popen(
            [sys.executable, "-c", LAUNCH, str(self.port), "1" if nocache else "0"],
            cwd=REPO,
            env={**os.environ, **env},
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self.client = httpx.Client(timeout=TIMEOUT)
        end = time.monotonic() + 90
        while time.monotonic() < end:
            try:
                if self.client.get(f"{self.url}/health").status_code == 200:
                    return
            except httpx.HTTPError:
                time.sleep(0.2)
        self.close()
        raise RuntimeError("the API did not start")

    def call(self, op: dict) -> tuple[float, int, int, int]:
        """(ms, status, decoded bytes, longest list) of one GraphQL call."""
        body = {"query": op["query"], "variables": op["variables"]}
        t0 = time.perf_counter()
        r = self.client.post(f"{self.url}/graphql", json=body)
        ms = (time.perf_counter() - t0) * 1000
        rows = 0
        if r.status_code == 200:
            rows = largest_list(r.json().get("data"))
        return ms, r.status_code, len(r.content), rows

    def close(self) -> None:
        self.client.close()
        self.proc.terminate()
        self.proc.wait(timeout=15)


def measure(ops: dict[str, dict]) -> dict[str, dict]:
    """Cold (a new process per operation), then warm (same process) per operation, then nocache."""
    out: dict[str, dict] = {}
    for name, op in ops.items():
        api = Api(nocache=False)
        try:
            cold, status, size, rows = api.call(op)
            warm = [api.call(op)[0] for _ in range(REPEATS)]
        finally:
            api.close()
        out[name] = {
            "status": status,
            "cold_ms": cold,
            "warm_p50_ms": statistics.median(warm),
            "warm_p95_ms": percentile(warm, 95),
            "bytes": size,
            "rows": rows,
        }
        print(f"  {name}: cold {cold:.0f} ms, warm p50 {statistics.median(warm):.1f} ms")
    api = Api(nocache=True)
    try:
        for name, op in ops.items():
            api.call(op)  # primed: the process-level state is warm, only the cache is absent
            raw = [api.call(op)[0] for _ in range(REPEATS)]
            out[name]["nocache_p50_ms"] = statistics.median(raw)
            out[name]["nocache_p95_ms"] = percentile(raw, 95)
    finally:
        api.close()
    return out


def page_totals(by_page: dict[str, list[str]], ops: dict[str, dict]) -> dict[str, dict]:
    """Per route: the on-load operations, their sum and critical path (the slowest: the browser
    sends them in parallel) for cold, warm p50 and nocache p50."""
    totals: dict[str, dict] = {}
    for route, names in by_page.items():
        row: dict = {"ops": names, "count": len(names)}
        for key in ("cold_ms", "warm_p50_ms", "nocache_p50_ms"):
            vals = [ops[n][key] for n in names if n in ops]
            row[f"sum_{key}"] = sum(vals)
            row[f"critical_{key}"] = max(vals, default=0.0)
        row["slowest"] = max(names, key=lambda n: ops[n]["cold_ms"], default="")
        totals[route] = row
    return totals


def render(report: dict) -> str:
    ops, pages = report["operations"], report["pages"]
    used: dict[str, list[str]] = defaultdict(list)
    for route, p in pages.items():
        for n in p["ops"]:
            used[n].append(route)
    lines = [
        "# API latency baseline",
        "",
        f"Generated by `make api-latency` ({report['generated']}); do not edit. The operations are "
        "what the web UI sends on page load (`make api-latency-capture`: every route in headless "
        "Chromium; no REST GET is fired on load, every read is GraphQL), measured against the "
        "real local store on an API this script starts itself.",
        "",
        "- **cold**: first call on a freshly started API process (one process per operation).",
        f"- **warm**: median / p95 of {REPEATS} repeat calls, response cache on (a hit where "
        "cacheable).",
        "- **nocache p50**: median of the same calls with the response cache bypassed: the "
        "resolver's cost.",
        "- **bytes**: decoded response body; **rows**: the longest list in it.",
        "",
        "| op | pages using it | cold ms | warm p50 | warm p95 | nocache p50 | bytes | rows |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for name, m in sorted(ops.items(), key=lambda kv: -kv[1]["cold_ms"]):
        n_more = len(used[name]) - 4
        where = ", ".join(used[name][:4]) + (f" +{n_more}" if n_more > 0 else "")
        note = "" if m["status"] == 200 else f" (HTTP {m['status']})"
        lines.append(
            f"| {name}{note} | {where or '-'} | {m['cold_ms']:.0f} | {m['warm_p50_ms']:.1f} | "
            f"{m['warm_p95_ms']:.1f} | {m['nocache_p50_ms']:.1f} | {m['bytes']:,} | {m['rows']} |"
        )
    lines += [
        "",
        "## Per page (on-load operations)",
        "",
        "Sum = all operations back to back; critical path = the slowest one (the browser sends "
        "them in parallel). Each page also fires the shell's Viewer, StatusStrip and Regime. Ops "
        "are distinct operation names (a page may send one several times, e.g. /guide/playbooks "
        "sends GuidePlaybook 20 times). Cold figures are each measured on a fresh process, so the "
        "cold sums count the process start-up cost (schema, store handles) once per op: read the "
        "critical path, and the warm / nocache sums, as the page's cost.",
        "",
        "| page | ops | sum cold | critical cold | sum warm p50 | sum nocache p50 | "
        "critical nocache | slowest (cold) |",
        "|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for route, p in sorted(pages.items(), key=lambda kv: -kv[1]["sum_cold_ms"]):
        lines.append(
            f"| `{route}` | {p['count']} | {p['sum_cold_ms']:.0f} | {p['critical_cold_ms']:.0f} | "
            f"{p['sum_warm_p50_ms']:.1f} | {p['sum_nocache_p50_ms']:.1f} | "
            f"{p['critical_nocache_p50_ms']:.1f} | {p['slowest']} |"
        )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    p.add_argument("--only", nargs="+", help="measure only these operations (writes nothing)")
    args = p.parse_args(argv)
    pages = json.loads(PAGES_FILE.read_text())["pages"]
    ops, by_page = inventory(pages)
    if args.only:
        ops = {k: v for k, v in ops.items() if k in args.only}
    print(f"{len(ops)} operations, {len(by_page)} pages")
    measured = measure(ops)
    if args.only:
        print(json.dumps(measured, indent=1))
        return 0
    report = {
        "generated": f"{datetime.now(UTC):%Y-%m-%d %H:%M UTC}",
        "repeats": REPEATS,
        "operations": measured,
        "pages": page_totals(by_page, measured),
    }
    JSON_OUT.write_text(json.dumps(report, indent=1) + "\n")
    DOC_OUT.parent.mkdir(parents=True, exist_ok=True)
    DOC_OUT.write_text(render(report))
    print(f"written {JSON_OUT.relative_to(REPO)}, {DOC_OUT.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
