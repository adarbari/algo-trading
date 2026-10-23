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

Every run records, per call, the HTTP status, the first GraphQL error and an empty-`data` check
(a fast failure is a FAILED row, never a fast call), the response bytes and the rows. The
uncached run's COLD pass uses the uncached mode (no cache or warmer replay can answer it) and is
flagged when its answer is far smaller than the later uncached one. `--page ROUTE` (repeatable)
and `--ops NAME ...` measure only those operations (writes nothing); `--profile --page ROUTE`
profiles each of the page's operations once, uncached, in process (`page_profile.py`, ->
docs/perf/page-profiles.md). Every mode stops with exit code 3 (partial results kept) when free
swap is under `--min-free-swap-mb` (500).

`--view VIEW_ID` (repeatable) is `--page` for one VIEW of `benchmarks/api_latency_views.json`
(route + search + the clicks that reach a sub-view, e.g. `/edges?edge={edge} > tab:...`; list
them in docs/perf/view-coverage.md): the operations and variables the crawler captured for it,
else its static ones; the same guards apply (`--profile --view ID` profiles one view).
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
import page_map
import page_profile as pp
import views as vw
import web_page_ops as wpo

REPO = Path(__file__).resolve().parents[2]
WEB_SRC = REPO / "apps/web/src"
PAGES_FILE = REPO / "benchmarks/api_latency_pages.json"
JSON_OUT = REPO / "benchmarks/api_latency.json"
DOC_OUT = REPO / "docs/perf/api-latency-baseline.md"
UNCACHED_JSON_OUT = REPO / "benchmarks/api_latency_uncached.json"
UNCACHED_DOC_OUT = REPO / "docs/perf/api-latency-uncached.md"
PROFILE_DOC_OUT = REPO / "docs/perf/page-profiles.md"
REPEATS = 10
UNCACHED_REPEATS = 5
LOAD_CLIENTS = 4
TIMEOUT = 180.0
GUARD_PATH: list[Path | None] = [None]  # the clone: its disk is watched too (set in main)
SWAP_FLOOR_MB = [pp.MIN_FREE_SWAP_MB]  # --min-free-swap-mb overrides it for the run
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
    except (ValueError, AttributeError):
        return "not JSON"
    if not errors:
        return None
    first = errors[0]
    return str(first.get("message", first) if isinstance(first, dict) else first)[:80]


def has_content(data: object) -> bool:
    """Whether ``data`` holds any non-null scalar (an answer of nulls and empty lists does not)."""
    if isinstance(data, list):
        return any(has_content(x) for x in data)
    if isinstance(data, dict):
        return any(has_content(v) for v in data.values())
    return data is not None


def answer_problem(status: int, content: bytes) -> str | None:
    """Why an answer is a failure: ``response_error`` (HTTP status, GraphQL error, non-JSON). An
    empty ``data`` is not one (a page can be legitimately empty): see ``empty_note``."""
    return response_error(status, content)


def empty_note(status: int, content: bytes) -> str | None:
    """ "EMPTY (check)" for a 200 answer whose ``data`` holds nothing but nulls and empty lists:
    to be looked at, not a failure."""
    if status != 200:
        return None
    try:
        data = json.loads(content).get("data")
    except (ValueError, AttributeError):
        return None
    return None if has_content(data) else "EMPTY (check): data is all null / empty"


def cold_suspect(cold_bytes: int, uncached_bytes: int, ratio: float = 0.5) -> str | None:
    """A message when the COLD answer is much smaller than the later uncached one (the cold call
    did not go through the resolver: a cache or an error answered it)."""
    if uncached_bytes and cold_bytes < ratio * uncached_bytes:
        return (
            f"cold answer {cold_bytes:,} B vs {uncached_bytes:,} B uncached: "
            "it did not go through the resolver"
        )
    return None


def cold_line(
    name: str, ms: float, size: int, rows: int, error: str | None, note: str | None = None
) -> str:
    """The progress line of one COLD call: time, bytes, rows and the first error."""
    return (
        f"  {name}: cold {ms:.0f} ms, {size:,} B, {rows} rows"
        + (f"  FAILED: {error}" if error else "")
        + (f"  {note}" if note else "")
    )


def guard() -> None:
    """Stop (SwapLowError) before an operation when free swap is under the floor or the clone's
    disk has under 8 GB free."""
    pp.swap_guard(SWAP_FLOOR_MB[0], disk_path=GUARD_PATH[0])


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
        self.mode = mode
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
        self.client = httpx.Client(timeout=TIMEOUT)
        try:
            self._start(env)
        except BaseException:  # a Ctrl-C / SIGTERM during start-up must not orphan the process
            self.close()
            raise

    def _start(self, env: dict[str, str]) -> None:
        self.proc = subprocess.Popen(
            [sys.executable, "-c", LAUNCH, str(self.port), MODES[self.mode]],
            cwd=REPO,
            env={**os.environ, **env},
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        end = time.monotonic() + 90
        while time.monotonic() < end:
            try:
                if self.client.get(f"{self.url}/health").status_code == 200:
                    return
            except httpx.HTTPError:
                time.sleep(0.2)
            if self.proc.poll() is not None:  # e.g. the patch's assert failed
                raise RuntimeError(f"the API exited with {self.proc.returncode} at start-up")
        raise RuntimeError("the API did not start")

    last_error: str | None = None
    last_note: str | None = None

    def call(self, op: dict) -> tuple[float, int, int, int]:
        """(ms, status, decoded bytes, longest list) of one GraphQL call."""
        body = {"query": op["query"], "variables": op["variables"]}
        t0 = time.perf_counter()
        try:
            r = self.client.post(f"{self.url}/graphql", json=body)
        except httpx.TimeoutException:  # a call over TIMEOUT is a FAILED row, not a crashed run
            self.last_error = f"timed out after {TIMEOUT:.0f} s"
            return (time.perf_counter() - t0) * 1000, 0, 0, 0
        ms = (time.perf_counter() - t0) * 1000
        rows = 0
        self.last_error = answer_problem(r.status_code, r.content)
        self.last_note = empty_note(r.status_code, r.content)
        if r.status_code == 200:
            rows = largest_list(r.json().get("data"))
        return ms, r.status_code, len(r.content), rows

    def close(self) -> None:
        self.client.close()
        if not hasattr(self, "proc"):  # never started
            return
        self.proc.terminate()
        try:
            self.proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait(timeout=15)


def measure(ops: dict[str, dict], **target: object) -> dict[str, dict]:
    """Cold (a new process per operation), then warm (same process) per operation, then nocache."""
    out: dict[str, dict] = {}
    try:
        _measure_into(out, ops, **target)
    except pp.SwapLowError as err:
        err.partial = out  # type: ignore[attr-defined]
        raise
    return out


def _measure_into(out: dict[str, dict], ops: dict[str, dict], **target: object) -> None:
    for name, op in ops.items():
        guard()
        api = Api(**target)  # type: ignore[arg-type]
        try:
            cold, status, size, rows = api.call(op)
            cold_error = api.last_error
            warm = [api.call(op)[0] for _ in range(REPEATS)]
        finally:
            api.close()
        out[name] = {
            "error": cold_error,
            "status": status,
            "cold_ms": cold,
            "warm_p50_ms": statistics.median(warm),
            "warm_p95_ms": percentile(warm, 95),
            "bytes": size,
            "rows": rows,
        }
        print(
            cold_line(name, cold, size, rows, cold_error)
            + f", warm p50 {statistics.median(warm):.1f} ms"
        )
    api = Api("nocache", **target)  # type: ignore[arg-type]
    try:
        for name, op in ops.items():
            guard()
            api.call(op)  # primed: the process-level state is warm, only the cache is absent
            raw = [api.call(op)[0] for _ in range(REPEATS)]
            out[name]["nocache_p50_ms"] = statistics.median(raw)
            out[name]["nocache_p95_ms"] = percentile(raw, 95)
    finally:
        api.close()


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
        if m.get("error"):
            note += f" **COLD FAILED: {m['error']}**"
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


def measure_cold(ops: dict[str, dict], mode: str = "cache", **target: object) -> dict[str, dict]:
    """COLD: the first call on a freshly started process, one new process per operation. The
    row keeps the first GraphQL error or empty-data problem (``cold_error``): a fast failure is
    flagged, never read as a fast call. ``mode`` "uncached" makes the call go through the
    resolver by construction (no cache, no warmer replay can answer it)."""
    out: dict[str, dict] = {}
    for name, op in ops.items():
        try:
            guard()
        except pp.SwapLowError as err:
            err.partial = out  # type: ignore[attr-defined]
            raise
        api = Api(mode, **target)  # type: ignore[arg-type]
        try:
            ms, status, size, rows = api.call(op)
            error, note = api.last_error, api.last_note
        finally:
            api.close()
        out[name] = {
            "status": status,
            "cold_ms": ms,
            "bytes": size,
            "rows": rows,
            "cold_error": error,
            "cold_note": note,
        }
        print(cold_line(name, ms, size, rows, error, note), flush=True)
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
                try:
                    r = await client.post(f"{url}/graphql", json=body)
                except httpx.TimeoutException:
                    out.append(
                        ((time.perf_counter() - t0) * 1000, f"timed out after {TIMEOUT:.0f} s")
                    )
                    continue
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
            try:
                guard()
            except pp.SwapLowError as err:
                err.partial = out  # type: ignore[attr-defined]
                raise
            solo: list[float] = []
            errors: list[str] = []
            size = 0
            for _ in range(UNCACHED_REPEATS):
                call = api.call(op)
                solo.append(call[0])
                size = max(size, call[2])
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
                "uncached_bytes": size,
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


request_counts = page_map.request_counts
calls_per_page = page_map.calls_per_page
page_report = page_map.page_report
render_pages = page_map.render_pages


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
        if m.get("cold_error"):
            note += f" **COLD FAILED: {m['cold_error']}** (cold ms is an error)"
        if m.get("cold_note"):
            note += f" **{m['cold_note']}**"
        if m.get("cold_flag"):
            note += f" **COLD SUSPECT: {m['cold_flag']}**"
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
    """The --uncached run: cold, uncached and under-load per operation, then the page tables. COLD
    runs in the uncached mode (the resolver answers by construction); a cold answer much smaller
    than the uncached one, or a cold error, flags the row."""
    target: dict[str, object] = {"data_url": args.data_url}
    tmp = Path(tempfile.mkdtemp(prefix="api-latency-config-"))
    measured: dict[str, dict] = {}
    try:
        target["config_dir"] = uncached_config(Path(args.config_dir or REPO / "config"), tmp / "c")
        try:
            measured.update(measure_cold(ops, "uncached", **target))
            for name, m in measure_uncached(ops, **target).items():
                measured[name].update(m)
        except pp.SwapLowError as err:
            for name, m in getattr(err, "partial", {}).items():
                measured.setdefault(name, {}).update(m)
            print(f"aborted: {err}; partial results:", file=sys.stderr)
            print(json.dumps(measured, indent=1))
            return pp.EXIT_LOW_SWAP
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    for m in measured.values():
        m["cold_flag"] = (
            None if m.get("cold_error") else cold_suspect(m["bytes"], m["uncached_bytes"])
        )
    if args.subset:
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


def run_profile(args: argparse.Namespace, ops: dict[str, dict]) -> int:
    """--profile: one uncached call per operation of the page, in this process, under cProfile."""
    tmp = Path(tempfile.mkdtemp(prefix="api-latency-config-"))
    try:
        config = uncached_config(Path(args.config_dir or REPO / "config"), tmp / "c")
        label = args.page[0] if args.page else "ops: " + ", ".join(ops)
        return pp.run_profile(
            ops,
            label,
            patch=PATCH,
            data_url=args.data_url,
            config_dir=config,
            out=Path(args.profile_out) if args.profile_out else PROFILE_DOC_OUT,
            problem=answer_problem,
            rows_of=largest_list,
            min_free_mb=SWAP_FLOOR_MB[0],
            disk_path=GUARD_PATH[0],
            notes_of=empty_note,
            limit_s=args.profile_limit,
            snapshot_s=args.profile_snapshot,
        )
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    p.add_argument(
        "--only", "--ops", nargs="+", help="measure only these operations (writes nothing)"
    )
    p.add_argument(
        "--page",
        action="append",
        default=[],
        metavar="ROUTE",
        help="measure only the operations of this route (repeatable; writes nothing)",
    )
    p.add_argument(
        "--view",
        action="append",
        default=[],
        metavar="VIEW_ID",
        help="measure only the operations of this view of the views file (repeatable; "
        "writes nothing)",
    )
    p.add_argument("--uncached", action="store_true", help="truly uncached + calls per page")
    p.add_argument(
        "--profile",
        action="store_true",
        help="one uncached call per operation of ONE --page (or of --ops) in process under "
        "cProfile -> docs/perf/page-profiles.md",
    )
    p.add_argument(
        "--profile-out",
        metavar="FILE",
        help="--profile: write here, not docs/perf/page-profiles.md",
    )
    p.add_argument(
        "--profile-limit",
        type=float,
        metavar="SECONDS",
        help="--profile: cut an operation after this long and write its partial profile "
        "(default: never)",
    )
    p.add_argument(
        "--profile-snapshot",
        type=float,
        default=pp.SNAPSHOT_S,
        metavar="SECONDS",
        help="--profile: take a profile snapshot (the trend table) this often (default 60)",
    )
    p.add_argument(
        "--min-free-swap-mb",
        type=float,
        default=pp.MIN_FREE_SWAP_MB,
        help="abort (exit 3, partial results kept) when free swap falls below this",
    )
    p.add_argument("--data-url", help="the store to serve (a clone); default: the real local store")
    p.add_argument("--config-dir", help="the config root (default ./config)")
    p.add_argument(
        "--i-know-this-is-the-real-store",
        action="store_true",
        help="allow --data-url to be the real local store (and --uncached without one)",
    )
    return p.parse_args(argv)


def run_needs_url(args: argparse.Namespace) -> bool:
    """The modes that must name a clone: any run but the whole-site baseline (a subset run
    starts an API too, and would otherwise default to the real store)."""
    return bool(args.uncached or args.profile or args.page or args.view or args.only)


def profile_selection_error(args: argparse.Namespace) -> str | None:
    """--profile runs one page (one process per page) or named operations, never none or two."""
    if (args.profile_limit is not None and args.profile_limit <= 0) or args.profile_snapshot <= 0:
        return "--profile-limit and --profile-snapshot must be positive seconds"
    if not args.profile:
        return None
    if len(args.page) + len(args.view) > 1:
        return "--profile takes one --page or --view per run (one process per page)"
    if not args.page and not args.view and not args.only:
        return "--profile needs --page ROUTE, --view VIEW_ID or --ops NAME ..."
    return None


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    SWAP_FLOOR_MB[0] = args.min_free_swap_mb
    # a SIGTERM (a stopped run) must unwind through the `finally` that stops the API processes
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))
    try:
        if message := profile_selection_error(args):
            raise RefusalError(message)
        args.data_url = check_target(
            args.data_url,
            real_stores(dict(os.environ), REPO, main_checkout_of(REPO)),
            args.i_know_this_is_the_real_store and not args.profile,  # never for --profile
            need_url=run_needs_url(args),
        )
    except RefusalError as err:
        print(f"refused: {err}", file=sys.stderr)
        return 2
    GUARD_PATH[0] = store_path(args.data_url) if args.data_url else None
    pages = json.loads(PAGES_FILE.read_text())["pages"]
    ops, by_page = inventory(pages)
    if args.view:
        try:
            view_ops, by_view = vw.view_operations(vw.load_views(), args.view, ops)
        except vw.SelectionError as err:
            print(f"refused: {err}", file=sys.stderr)
            return 2
        ops, by_page = {**ops, **view_ops}, {**by_page, **by_view}
        args.page = [*args.page, *args.view]  # a view is measured as a page of its own
    args.subset = bool(args.only or args.page)
    if args.subset:
        try:
            ops = pp.select_operations(
                ops, by_page, args.page, args.only or [], static_routes(args.page, by_page)
            )
        except pp.SelectionError as err:
            print(f"refused: {err}", file=sys.stderr)
            return 2
    print(f"{len(ops)} operations, {len(by_page)} pages", flush=True)
    if args.profile:
        return run_profile(args, ops)
    if args.uncached:
        return run_uncached(args, ops, request_counts(pages), pages)
    return run_baseline(args, ops, by_page)


def run_baseline(
    args: argparse.Namespace, ops: dict[str, dict], by_page: dict[str, list[str]]
) -> int:
    """The plain baseline: cold, warm and nocache per operation."""
    target: dict[str, object] = {}
    if args.data_url:
        target["data_url"] = args.data_url
    if args.config_dir:
        target["config_dir"] = Path(args.config_dir)
    try:
        measured = measure(ops, **target)
    except pp.SwapLowError as err:
        print(f"aborted: {err}; partial results:", file=sys.stderr)
        print(json.dumps(getattr(err, "partial", {}), indent=1))
        return pp.EXIT_LOW_SWAP
    if args.subset:
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


def static_routes(routes: list[str], by_page: dict[str, list[str]]) -> dict[str, list[str]]:
    """The static on-load operations of the --page routes the capture has no entry for."""
    missing = [r for r in routes if r not in by_page]
    if not missing or not WEB_SRC.is_dir():
        return {}
    static, shell = wpo.static_page_ops(WEB_SRC, wpo.enumerate_routes(WEB_SRC))
    return {
        r: [*shell, *(o for o, k in static[r].items() if k == wpo.LOAD)]
        for r in missing
        if r in static
    }


if __name__ == "__main__":
    raise SystemExit(main())
