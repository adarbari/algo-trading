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

`--uncached` (docs/perf/api-latency-uncached.md, benchmarks/api_latency_uncached.json) measures
the truly uncached cost: neither the response cache NOR the in-process loader `ResultCache`
answers, and the config copy it runs on has `serving.release_reads = false` (the serving release
is a persisted answer too). Per operation: COLD (fresh process), UNCACHED (N=5 calls, none
discarded), UNCACHED-UNDER-LOAD (K=4 concurrent clients, to expose GIL contention); per page the
requests per operation (repeats counted), their bytes and the share of the page's time. Needs
`--data-url` (a CLONE of the store: the real one is refused unless
`--i-know-this-is-the-real-store`); `--config-dir` picks the config root (default ./config).
Runbook: docs/perf/api-latency-uncached-run.md.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import shutil
import signal
import socket
import statistics
import subprocess
import sys
import tempfile
import time
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

import httpx2 as httpx  # the httpx API; installed with the test dependencies

sys.path.insert(0, str(Path(__file__).resolve().parent))
import web_page_ops as wpo

REPO = Path(__file__).resolve().parents[2]
WEB_SRC = REPO / "apps/web/src"
PAGES_FILE = REPO / "benchmarks/api_latency_pages.json"
JSON_OUT = REPO / "benchmarks/api_latency.json"
DOC_OUT = REPO / "docs/perf/api-latency-baseline.md"
UNCACHED_JSON_OUT = REPO / "benchmarks/api_latency_uncached.json"
UNCACHED_DOC_OUT = REPO / "docs/perf/api-latency-uncached.md"
REPEATS = 10
UNCACHED_REPEATS = 5
LOAD_CLIENTS = 4
TIMEOUT = 120.0
PORT_OFFSET = 8  # spare ports: ALGOTRADE_PORT_BASE + 8 .. + 19 (release_writer_run.py uses + 7)
MODES = {"cache": "0", "nocache": "1", "uncached": "2"}
RELEASE_READS = re.compile(r"^(release_reads\s*=\s*)\w+", re.M)
# argv: port, mode ('0' cache on, '1' response cache never answers, '2' neither it nor the
# loaders' ResultCache answers: `get` finds nothing and `get_or_compute` always computes).
PATCH = """
import sys
mode = sys.argv[2]
import algotrade_api.graphql.response_cache as rc
import algotrade_api.graphql.warm as w
import algotrade.services.read.context as cx
assert all(hasattr(c, n) for c, n in [
    (rc.ResponseCache, 'get'), (rc.ResponseCache, 'get_stale'),
    (cx.ResultCache, 'get'), (cx.ResultCache, 'get_or_compute'),
    (w.CacheWarmer, 'run'), (w.CacheWarmer, 'warm_home'), (w.CacheWarmer, 'replay_operations'),
]), 'the perf patch targets moved: update PATCH in scripts/perf/api_latency.py'
async def _idle(self, *args):
    return None
if mode in ('1', '2'):
    rc.ResponseCache.get = lambda self, key: None
    rc.ResponseCache.get_stale = lambda self, key: None
if mode == '2':
    cx.ResultCache.get = lambda self, key: None
    cx.ResultCache.get_or_compute = lambda self, key, compute: compute()
    # the warmer replays every seeded operation in the background at start-up: uncached it
    # would load the process while COLD and the first UNCACHED calls are timed
    w.CacheWarmer.run = _idle
    w.CacheWarmer.replay_operations = _idle
    w.CacheWarmer.warm_home = lambda self, *args: None
"""
LAUNCH = (
    PATCH + "import uvicorn\n"
    "from algotrade_api.app import app\n"
    "uvicorn.run(app, host='127.0.0.1', port=int(sys.argv[1]), log_level='warning')\n"
)
# What still memoises under UNCACHED (listed in the generated doc; not bypassed).
REMAINING_MEMOS = (
    "`lru_cache` on GraphQL document parsing (`operation_name`, `release_selects_only` in "
    "graphql/response_cache.py; `only_inline` in graphql/offload.py): parse results only, no data",
    "`LocalStorage._dates_memo` (storage/backends/local.py): partition listings keyed by the "
    "store's sequence; it saves directory walks on every read",
    "the OS file cache and pyarrow's memory pool (a second read of a Parquet file is faster "
    "than the first): the cost here is with a warm OS cache, not a cold disk",
    "process singletons built at start-up or on first use (GraphQL schema, store handles, "
    "config); `ResultCache.put` still stores results (memory only, never read back)",
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


def response_error(status: int, content: bytes) -> str | None:
    """Why a response is not a success: its HTTP status, or the first GraphQL error message
    (a fast error is not a fast call)."""
    if status != 200:
        return f"HTTP {status}"
    try:
        errors = json.loads(content).get("errors")
    except ValueError:
        return "not JSON"
    return str(errors[0].get("message", errors[0]))[:80] if errors else None


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


def free_port(env: dict[str, str] | None = None) -> int:
    """A spare port: the first free one of ALGOTRADE_PORT_BASE + 8..19 (`source worktree.env`);
    never another port: the base unset, or every port busy, is an error."""
    base = (env if env is not None else os.environ).get("ALGOTRADE_PORT_BASE", "")
    if not base.isdigit():
        raise RuntimeError("ALGOTRADE_PORT_BASE is not set: `source worktree.env` first")
    for port in range(int(base) + PORT_OFFSET, int(base) + PORT_OFFSET + 12):
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", port))
            except OSError:
                continue
            return port
    raise RuntimeError(f"no free port in {int(base) + PORT_OFFSET}..{int(base) + PORT_OFFSET + 11}")


class RefusalError(Exception):
    """A guard stopped the run before any API was started."""


def store_path(url: str) -> Path:
    """The directory a ``file://`` data URL names (relative paths resolve against the cwd)."""
    parsed = urlparse(url)
    if parsed.scheme != "file":
        raise RefusalError(f"data URL {url!r}: only file:// stores are supported")
    path = Path(parsed.netloc + parsed.path).expanduser()
    return (path if path.is_absolute() else REPO / path).resolve()  # as the API resolves it


def real_stores(env: dict[str, str], repo: Path, main_checkout: Path | None) -> list[Path]:
    """Every directory that is the real local store: ``$ALGOTRADE_DATA_URL``, this checkout's
    ``var/data`` and the main checkout's."""
    found = [repo / "var" / "data"]
    if main_checkout is not None:
        found.append(main_checkout / "var" / "data")
    if env.get("ALGOTRADE_DATA_URL", "").startswith("file:"):
        found.append(store_path(env["ALGOTRADE_DATA_URL"]))
    return [p.resolve() for p in found]


def main_checkout_of(repo: Path) -> Path | None:
    """The main checkout (the parent of git's common dir) when ``repo`` is a worktree."""
    done = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "--path-format=absolute", "--git-common-dir"],
        capture_output=True,
        text=True,
        check=False,
    )
    return Path(done.stdout.strip()).parent if done.returncode == 0 and done.stdout else None


def check_target(
    data_url: str | None, stores: list[Path], confirmed: bool, need_url: bool
) -> str | None:
    """The data URL to run against, or a RefusalError when it is (or is inside, or contains) the
    real store without ``--i-know-this-is-the-real-store``. ``need_url``: the mode requires an
    explicit URL (the real store is then never reached by omission)."""
    if data_url is None:
        if need_url and not confirmed:
            raise RefusalError(
                "--uncached needs --data-url (a CLONE of the store); the real store only with "
                "--i-know-this-is-the-real-store"
            )
        return None
    path = store_path(data_url)
    for real in stores:
        if overlaps(path, real):
            if confirmed:
                return f"file://{path}"
            raise RefusalError(
                f"--data-url {data_url} is the real local store {real}: run on a clone, or pass "
                "--i-know-this-is-the-real-store"
            )
    return f"file://{path}"


def _chain(path: Path) -> list[Path]:
    """``path`` and its parents that exist (samefile needs them on disk)."""
    return [p for p in (path, *path.parents) if p.exists()]


def overlaps(a: Path, b: Path) -> bool:
    """Whether ``a`` is ``b``, inside it or contains it, by ``samefile`` (so a case-insensitive
    volume's other spelling or a symlink cannot slip through)."""
    inside = any(x.samefile(b) for x in _chain(a)) if b.exists() else False
    contains = a.exists() and any(a.samefile(y) for y in _chain(b))
    lexical = a == b or b in a.parents or a in b.parents  # neither need exist yet
    return inside or contains or lexical


def uncached_config(config_dir: Path, to: Path) -> Path:
    """A copy of the whole config root ``config_dir`` at ``to`` with ``release_reads`` false in
    ``site/nightly.toml``: the serving release answers listed operations from a persisted copy
    otherwise."""
    shutil.copytree(config_dir, to)
    nightly = to / "site" / "nightly.toml"
    text = nightly.read_text()
    if not RELEASE_READS.search(text):
        raise RefusalError(f"{nightly}: no release_reads line to override")
    nightly.write_text(RELEASE_READS.sub(r"\g<1>false", text, count=1))
    return to


class Api:
    """An API process of this script's own, on a spare port."""

    def __init__(
        self,
        mode: str = "cache",
        data_url: str | None = None,
        config_dir: Path | None = None,
    ) -> None:
        self.port = free_port()
        self.url = f"http://127.0.0.1:{self.port}"
        env = {
            "ALGOTRADE_AUTH": "off",
            "ALGOTRADE_LLM": "off",
            "ALGOTRADE_IBKR_PORT": "1",  # no broker: live quotes degrade, never hang
        }
        if data_url:
            env["ALGOTRADE_DATA_URL"] = data_url
        if config_dir:
            env["ALGOTRADE_CONFIG_DIR"] = str(config_dir)
        self.proc = subprocess.Popen(
            [sys.executable, "-c", LAUNCH, str(self.port), MODES[mode]],
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
            if self.proc.poll() is not None:  # e.g. the patch's assert failed
                self.client.close()
                raise RuntimeError(f"the API exited with {self.proc.returncode} at start-up")
        self.close()
        raise RuntimeError("the API did not start")

    last_error: str | None = None

    def call(self, op: dict) -> tuple[float, int, int, int]:
        """(ms, status, decoded bytes, longest list) of one GraphQL call."""
        body = {"query": op["query"], "variables": op["variables"]}
        t0 = time.perf_counter()
        r = self.client.post(f"{self.url}/graphql", json=body)
        ms = (time.perf_counter() - t0) * 1000
        rows = 0
        self.last_error = response_error(r.status_code, r.content)
        if r.status_code == 200:
            rows = largest_list(r.json().get("data"))
        return ms, r.status_code, len(r.content), rows

    def close(self) -> None:
        self.client.close()
        self.proc.terminate()
        try:
            self.proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait(timeout=15)


def measure(ops: dict[str, dict], **target: object) -> dict[str, dict]:
    """Cold (a new process per operation), then warm (same process) per operation, then nocache."""
    out: dict[str, dict] = {}
    for name, op in ops.items():
        api = Api(**target)  # type: ignore[arg-type]
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
    api = Api("nocache", **target)  # type: ignore[arg-type]
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
        "are distinct operation names (a page may send one several times, e.g. /guide/screeners "
        "sends GuideScreener 20 times). Cold figures are each measured on a fresh process, so the "
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


# ---- --uncached: the truly uncached cost, and the calls per page ----------------------------


def measure_cold(ops: dict[str, dict], **target: object) -> dict[str, dict]:
    """COLD: the first call on a freshly started process, one new process per operation."""
    out: dict[str, dict] = {}
    for name, op in ops.items():
        api = Api(**target)  # type: ignore[arg-type]
        try:
            ms, status, size, rows = api.call(op)
        finally:
            api.close()
        out[name] = {"status": status, "cold_ms": ms, "bytes": size, "rows": rows}
        print(f"  {name}: cold {ms:.0f} ms")
    return out


async def load_samples(
    url: str, op: dict, clients: int, repeats: int
) -> list[tuple[float, str | None]]:
    """(ms, error) of every call of ``clients`` concurrent clients, each firing ``repeats`` calls
    back to back (one HTTP client each, as separate browsers): the contention of one process's
    threads."""
    body = {"query": op["query"], "variables": op["variables"]}

    async def one() -> list[tuple[float, str | None]]:
        out: list[tuple[float, str | None]] = []
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            for _ in range(repeats):
                t0 = time.perf_counter()
                r = await client.post(f"{url}/graphql", json=body)
                out.append(
                    ((time.perf_counter() - t0) * 1000, response_error(r.status_code, r.content))
                )
        return out

    return [t for ts in await asyncio.gather(*(one() for _ in range(clients))) for t in ts]


def measure_uncached(ops: dict[str, dict], **target: object) -> dict[str, dict]:
    """UNCACHED: one process whose response cache, loader ResultCache and warmer are off; per
    operation ``UNCACHED_REPEATS`` calls (none discarded as priming), then the same op from
    ``LOAD_CLIENTS`` concurrent clients (UNCACHED-UNDER-LOAD). Calls that fail (HTTP status,
    GraphQL errors) are counted and the first error kept: the row is flagged."""
    out: dict[str, dict] = {}
    api = Api("uncached", **target)  # type: ignore[arg-type]
    try:
        for name, op in ops.items():
            solo: list[float] = []
            errors: list[str] = []
            for _ in range(UNCACHED_REPEATS):
                solo.append(api.call(op)[0])
                if api.last_error:
                    errors.append(api.last_error)
            sampled = asyncio.run(load_samples(api.url, op, LOAD_CLIENTS, UNCACHED_REPEATS))
            loaded = [ms for ms, _ in sampled]
            errors += [e for _, e in sampled if e]
            out[name] = {
                "uncached_p50_ms": statistics.median(solo),
                "uncached_p95_ms": percentile(solo, 95),
                "load_p50_ms": statistics.median(loaded),
                "load_p95_ms": percentile(loaded, 95),
                "failed_calls": len(errors),
                "first_error": errors[0] if errors else None,
            }
            print(
                f"  {name}: uncached p50 {out[name]['uncached_p50_ms']:.1f} ms, "
                f"under load p50 {out[name]['load_p50_ms']:.1f} ms"
                + (f"  FAILED x{len(errors)}: {errors[0]}" if errors else "")
            )
    finally:
        api.close()
    return out


def request_counts(pages: dict[str, list[dict]]) -> dict[str, dict[str, int]]:
    """Per route: operation name -> requests sent on load (repeats counted, GraphQL only)."""
    counts: dict[str, dict[str, int]] = {}
    for route, calls in pages.items():
        per: dict[str, int] = {}
        for call in calls:
            if call["kind"] == "graphql":
                per[call["op"]] = per.get(call["op"], 0) + 1
        counts[route] = per
    return counts


TIME_KEYS = ("cold_ms", "uncached_p50_ms", "load_p50_ms")


def calls_per_page(counts: dict[str, dict[str, int]], ops: dict[str, dict]) -> dict[str, dict]:
    """Per route: requests per operation with their bytes, ms and share of the page's time, the
    distinct operations, total requests, and for cold / uncached p50 / under-load p50 the sum
    (every request back to back, repeats counted) and the critical path (the slowest distinct
    operation: the browser sends them in parallel). Share = count * ms / sum, per time key."""
    pages: dict[str, dict] = {}
    for route, per in counts.items():
        total = sum(per.values())
        row: dict = {"distinct": len(per), "requests": total, "bytes": 0, "ops": {}}
        sums = {k: sum(n * ops[o][k] for o, n in per.items() if o in ops) for k in TIME_KEYS}
        for name, n in sorted(per.items(), key=lambda kv: -kv[1]):
            m = ops.get(name, {})
            entry = {"count": n, "bytes": n * m.get("bytes", 0), "unit_bytes": m.get("bytes", 0)}
            for k in TIME_KEYS:
                entry[k] = m.get(k, 0.0)
                entry[f"share_{k}"] = n * m.get(k, 0.0) / sums[k] if sums[k] else 0.0
            row["bytes"] += entry["bytes"]
            row["ops"][name] = entry
        for k in TIME_KEYS:
            row[f"sum_{k}"] = sums[k]
            row[f"critical_{k}"] = max((ops[o][k] for o in per if o in ops), default=0.0)
        pages[route] = row
    return pages


def captured_by_route(
    routes: list[str], capture: dict[str, list[dict]]
) -> tuple[dict[str, dict[str, int]], dict[str, list[str]], list[str]]:
    """Per route pattern: the requests per operation of its capture entries (the highest count
    over its URLs), the URLs it matched, and the capture URLs no route matches."""
    urls, orphans = wpo.match_capture(routes, list(capture))
    counts = request_counts(capture)
    merged: dict[str, dict[str, int]] = {}
    for route, matched in urls.items():
        per: dict[str, int] = {}
        for url in matched:
            for op, n in counts[url].items():
                per[op] = max(per.get(op, 0), n)
        merged[route] = per
    return merged, urls, orphans


def page_report(
    routes: list[wpo.Route],
    static: dict[str, dict[str, int]],
    shell: dict[str, int],
    capture: dict[str, list[dict]],
    ops: dict[str, dict],
    all_ops: set[str],
) -> dict:
    """The Pages section: per route the static classes, the captured counts, their differences
    and the times (from the capture when there is one, else the static on-load operations)."""
    patterns = [r.path for r in routes]
    captured, urls, orphans = captured_by_route(patterns, capture)
    shell_ops = set(shell)
    counts: dict[str, dict[str, int]] = {}
    rows: dict[str, dict] = {}
    for route in routes:
        st = static[route.path]
        cap = captured[route.path]
        cap_page = {o: n for o, n in cap.items() if o not in shell_ops}
        on_load = {o for o, k in st.items() if k == wpo.LOAD}
        diff = []
        if urls[route.path]:
            for o in sorted(set(cap_page) - set(st)):
                diff.append(f"{o}: captured, not in the static map (capture is right)")
            for o in sorted(on_load - set(cap_page)):
                diff.append(f"{o}: static on-load, not captured (capture used one parameter value)")
        counts[route.path] = (
            cap if urls[route.path] else {**dict.fromkeys(shell, 1), **dict.fromkeys(on_load, 1)}
        )
        rows[route.path] = {
            "kind": route.kind,
            "search_params": route.search,
            "file": route.file,
            "capture_urls": urls[route.path],
            "static_on_load": sorted(on_load),
            "static_uncertain": sorted(o for o, k in st.items() if k == wpo.MAYBE),
            "static_interaction": sorted(o for o, k in st.items() if k == wpo.HANDLER),
            "captured": cap_page,
            "differences": diff,
            "basis": "capture" if urls[route.path] else "static on-load",
        }
    timed = calls_per_page(counts, ops)
    for route, row in rows.items():
        t = timed[route]
        row.update({k: t[k] for k in t if k.startswith(("sum_", "critical_"))})
        row["requests"] = t["requests"]
    reached = set(shell) | {
        o
        for r in rows.values()
        for k in ("static_on_load", "static_uncertain", "static_interaction")
        for o in r[k]
    }
    reached |= {o for per in captured.values() for o in per}
    return {
        "pages": rows,
        "shell": dict(sorted(shell.items())),
        "routes_without_capture": [r for r, u in urls.items() if not u],
        "capture_without_route": orphans,
        "operations_without_page": sorted(all_ops - reached),
        "pages_without_data": [
            r
            for r, row in rows.items()
            if not row["captured"]
            and not row["static_on_load"]
            and not row["static_uncertain"]
            and not row["static_interaction"]
        ],
    }


def render_pages(rep: dict) -> list[str]:
    cls = {wpo.LOAD: "on-load", wpo.MAYBE: "uncertain", wpo.HANDLER: "interaction"}
    shell = ", ".join(f"{o} ({cls[k]})" for o, k in rep["shell"].items())
    lines = [
        "",
        "## Pages",
        "",
        "Every leaf route of the web router (`apps/web/src/app/routes`) with its path pattern "
        "(`$x` is a parameter; **search** = it declares search params). **Static** = the import "
        "walk from the route's page down to the `graphql()` documents "
        "(`scripts/perf/web_page_ops.py`), classed on-load (rendered or called "
        "unconditionally), uncertain (behind `&&`, `?`, an `enabled` option or a self-gated "
        "hook) or interaction-only (inside a handler or callback); the shell's operations are "
        f"listed once and removed from each page. Shell: {shell or '-'}. **Captured** = what the "
        "browser sent (`api_latency_pages.json`, requests per operation, shell excluded). The walk "
        "reads source text: a read reached through a prop, context or registry is not seen "
        "(the capture is right then); a conditional it cannot read counts as on-load. Times use "
        "the capture's requests (shell included) where the route has a capture, else the static "
        "on-load operations plus the shell once; sum = every request back to back, critical = "
        "the slowest operation.",
        "",
        "| page | kind | static on-load | captured (requests) | differences | interaction-only "
        "(uncertain) | sum uncached p50 | critical uncached p50 | critical cold | basis |",
        "|---|---|---|---|---|---|---:|---:|---:|---|",
    ]
    for route, r in sorted(rep["pages"].items()):
        cap = ", ".join(f"{o} x{n}" if n > 1 else o for o, n in r["captured"].items()) or "-"
        extra = r["static_interaction"] + [f"{o}?" for o in r["static_uncertain"]]
        lines.append(
            f"| `{route}`{' search' if r['search_params'] else ''} | {r['kind']} | "
            f"{', '.join(r['static_on_load']) or '-'} | {cap} | "
            f"{'; '.join(r['differences']) or '-'} | {', '.join(extra) or '-'} | "
            f"{r['sum_uncached_p50_ms']:.0f} | {r['critical_uncached_p50_ms']:.0f} | "
            f"{r['critical_cold_ms']:.0f} | {r['basis']} |"
        )
    params = [f"`{u}`" for r in rep["pages"].values() for u in r["capture_urls"]]
    lines += [
        "",
        "Capture URLs (the parameter values the capture used): " + (", ".join(params) or "-"),
        "",
        "Routes with no capture entry: "
        + (", ".join(f"`{r}`" for r in rep["routes_without_capture"]) or "none"),
        "",
        "Capture entries that match no route: "
        + (", ".join(f"`{r}`" for r in rep["capture_without_route"]) or "none"),
        "",
        "### Operations without a page",
        "",
        "Query documents in the web source that no route reaches (statically, shell included) "
        "and the capture never sent: " + (", ".join(rep["operations_without_page"]) or "none"),
        "",
        "### Pages without data",
        "",
        "Routes with no operation, static or captured: "
        + (", ".join(f"`{r}`" for r in rep["pages_without_data"]) or "none"),
        "",
    ]
    return lines


def render_uncached(report: dict) -> str:
    ops, pages = report["operations"], report["pages"]
    lines = [
        "# API latency, truly uncached, and calls per page",
        "",
        f'Generated by `make api-latency ARGS="--uncached --data-url ..."` '
        f"({report['generated']}); do not edit. Runbook: `docs/perf/api-latency-uncached-run.md`. "
        f"Target: `{report['target']}`.",
        "",
        "- **cold**: first call on a freshly started process (one process per operation).",
        "- **uncached**: the response cache and the loaders' `ResultCache` never answer, and "
        "`serving.release_reads` is false: median / p95 of "
        f"{report['uncached_repeats']} calls, none discarded as priming.",
        f"- **under load**: the same operation from {report['load_clients']} concurrent clients "
        f"({report['uncached_repeats']} calls each) on the uncached process: median / p95 of all "
        "calls; the gap to **uncached** is GIL and pool contention.",
        "- **bytes**: decoded response body; **rows**: the longest list in it.",
        "",
        "Still memoised (not bypassed):",
        "",
        *[f"- {m}" for m in report["remaining_memos"]],
        "",
        "| op | cold ms | uncached p50 | uncached p95 | under load p50 | under load p95 | "
        "load / solo | bytes | rows |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name, m in sorted(ops.items(), key=lambda kv: -kv[1]["uncached_p50_ms"]):
        ratio = m["load_p50_ms"] / m["uncached_p50_ms"] if m["uncached_p50_ms"] else 0.0
        note = "" if m["status"] == 200 else f" (HTTP {m['status']})"
        if m.get("failed_calls"):
            note += f" **FAILED x{m['failed_calls']}: {m['first_error']}** (timings are errors)"
        lines.append(
            f"| {name}{note} | {m['cold_ms']:.0f} | {m['uncached_p50_ms']:.1f} | "
            f"{m['uncached_p95_ms']:.1f} | {m['load_p50_ms']:.1f} | {m['load_p95_ms']:.1f} | "
            f"{ratio:.1f}x | {m['bytes']:,} | {m['rows']} |"
        )
    lines += [
        "",
        "## Calls per page",
        "",
        "Requests each route sends on load, per operation (repeats counted: a page that sends "
        "GuideScreener 20 times shows 20). Sum = every request back to back; critical path = the "
        "slowest distinct operation (the browser sends them in parallel). Bytes are per page "
        "(count x one response); share = the operation's share of the page's summed uncached p50.",
        "",
        "| page | requests | distinct ops | bytes | sum cold | critical cold | sum uncached p50 | "
        "critical uncached p50 | sum under load p50 | critical under load p50 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    ranked = sorted(pages.items(), key=lambda kv: -kv[1]["sum_uncached_p50_ms"])
    for route, p in ranked:
        lines.append(
            f"| `{route}` | {p['requests']} | {p['distinct']} | {p['bytes']:,} | "
            f"{p['sum_cold_ms']:.0f} | {p['critical_cold_ms']:.0f} | "
            f"{p['sum_uncached_p50_ms']:.0f} | {p['critical_uncached_p50_ms']:.0f} | "
            f"{p['sum_load_p50_ms']:.0f} | {p['critical_load_p50_ms']:.0f} |"
        )
    lines += ["", "### Per page, per operation", ""]
    for route, p in ranked:
        lines += [
            f"**`{route}`**",
            "",
            "| op | requests | bytes | uncached p50 ms | share of page |",
            "|---|---:|---:|---:|---:|",
        ]
        for name, e in p["ops"].items():
            lines.append(
                f"| {name} | {e['count']} | {e['bytes']:,} | {e['uncached_p50_ms']:.1f} | "
                f"{e['share_uncached_p50_ms']:.0%} |"
            )
        lines.append("")
    lines += render_pages(report["page_map"]) if "page_map" in report else []
    return "\n".join(lines)


def run_uncached(
    args: argparse.Namespace, ops: dict[str, dict], counts: dict, capture: dict
) -> int:
    """The --uncached run: cold, uncached and under-load per operation, then the page tables."""
    target: dict[str, object] = {"data_url": args.data_url}
    tmp = Path(tempfile.mkdtemp(prefix="api-latency-config-"))
    try:
        target["config_dir"] = uncached_config(Path(args.config_dir or REPO / "config"), tmp / "c")
        measured = measure_cold(ops, **target)
        for name, m in measure_uncached(ops, **target).items():
            measured[name].update(m)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    if args.only:
        print(json.dumps(measured, indent=1))
        return 0
    report = {
        "generated": f"{datetime.now(UTC):%Y-%m-%d %H:%M UTC}",
        "target": args.data_url or "the real local store",
        "uncached_repeats": UNCACHED_REPEATS,
        "load_clients": LOAD_CLIENTS,
        "remaining_memos": list(REMAINING_MEMOS),
        "operations": measured,
        "pages": calls_per_page(counts, measured),
    }
    if WEB_SRC.is_dir():
        routes = wpo.enumerate_routes(WEB_SRC)
        static, shell = wpo.static_page_ops(WEB_SRC, routes)
        report["page_map"] = page_report(
            routes, static, shell, capture, measured, wpo.all_query_ops(WEB_SRC)
        )
    UNCACHED_JSON_OUT.write_text(json.dumps(report, indent=1) + "\n")
    UNCACHED_DOC_OUT.write_text(render_uncached(report))
    print(f"written {UNCACHED_JSON_OUT.relative_to(REPO)}, {UNCACHED_DOC_OUT.relative_to(REPO)}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    p.add_argument("--only", nargs="+", help="measure only these operations (writes nothing)")
    p.add_argument("--uncached", action="store_true", help="truly uncached + calls per page")
    p.add_argument("--data-url", help="the store to serve (a clone); default: the real local store")
    p.add_argument("--config-dir", help="the config root (default ./config)")
    p.add_argument(
        "--i-know-this-is-the-real-store",
        action="store_true",
        help="allow --data-url to be the real local store (and --uncached without one)",
    )
    args = p.parse_args(argv)
    # a SIGTERM (a stopped run) must unwind through the `finally` that stops the API processes
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))
    try:
        args.data_url = check_target(
            args.data_url,
            real_stores(dict(os.environ), REPO, main_checkout_of(REPO)),
            args.i_know_this_is_the_real_store,
            need_url=args.uncached,
        )
    except RefusalError as err:
        print(f"refused: {err}", file=sys.stderr)
        return 2
    pages = json.loads(PAGES_FILE.read_text())["pages"]
    ops, by_page = inventory(pages)
    if args.only:
        ops = {k: v for k, v in ops.items() if k in args.only}
    print(f"{len(ops)} operations, {len(by_page)} pages")
    if args.uncached:
        return run_uncached(args, ops, request_counts(pages), pages)
    target: dict[str, object] = {}
    if args.data_url:
        target["data_url"] = args.data_url
    if args.config_dir:
        target["config_dir"] = Path(args.config_dir)
    measured = measure(ops, **target)
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
