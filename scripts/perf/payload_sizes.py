"""What each page's GraphQL operations weigh on the wire.

By hand against a SPARE API, never the live one and never in CI:
``ALGOTRADE_AUTH=off .venv/bin/algotrade-api --port 8011`` then
``.venv/bin/python scripts/perf/payload_sizes.py --url http://127.0.0.1:8011``.
Per page it sends the shell's operations and the page's own (the mix ``load.py`` replays, the
documents parsed from the web's generated ``gql.ts``), one at a time, and reports for each the raw
JSON bytes, the bytes on the wire with ``Accept-Encoding: gzip`` (what a distant client downloads)
and the server time of a warm second pass. The page's wire total and a transfer estimate over a
link (``--rtt-ms``, ``--mbit``: the serial round trips plus the bytes at the link's speed) close
each table. Writes ``var/perf/payload-sizes.json``.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

import httpx2 as httpx  # the httpx API; installed with the test dependencies

sys.path.insert(0, str(Path(__file__).resolve().parent))
import load

SLOW_MS = 5000.0  # an operation slower than this on its first call is not repeated


@dataclass
class OpSize:
    page: str
    op: str
    raw_bytes: int
    wire_bytes: int
    encoding: str
    warm_ms: float


def link_seconds(wire_bytes: int, rtt_s: float, mbit: float) -> float:
    """One request over a link: a round trip plus the bytes at the link's speed."""
    return rtt_s + wire_bytes * 8 / (mbit * 1_000_000)


async def measure_op(client, docs: dict[str, str], op: load.Op, session: date) -> tuple:
    payload = {"query": docs[op.name], "variables": op.variables(session)}
    headers = {"accept-encoding": "gzip"}
    started = time.perf_counter()
    r = await client.post("/graphql", json=payload, headers=headers)
    elapsed = (time.perf_counter() - started) * 1000
    r.raise_for_status()
    return len(r.content), r.num_bytes_downloaded, r.headers.get("content-encoding", ""), elapsed


async def resolve_session(url: str) -> date:
    """The session the API serves; the first call on a cold API can take minutes."""
    async with httpx.AsyncClient(base_url=url, timeout=600.0) as c:
        r = await c.post("/graphql", json={"query": "{ session { date } }"})
        r.raise_for_status()
        return date.fromisoformat(r.json()["data"]["session"]["date"])


async def run(url: str) -> list[OpSize]:
    docs = load.parse_documents(load.GQL_TS.read_text())
    session = await resolve_session(url)
    sizes: list[OpSize] = []
    seen: set[str] = set()
    async with httpx.AsyncClient(base_url=url, timeout=180.0) as client:
        for page in load.PAGES:
            for op in load.page_ops(page):
                key = f"{page}/{op.name}"
                if key in seen:
                    continue
                seen.add(key)
                try:
                    raw, wire, encoding, ms = await measure_op(client, docs, op, session)
                    if ms < SLOW_MS:  # a warm second pass, unless the first was a cold crawl
                        raw, wire, encoding, ms = await measure_op(client, docs, op, session)
                except httpx.HTTPError as exc:
                    print(f"{key}: {type(exc).__name__}", file=sys.stderr)
                    sizes.append(OpSize(page, op.name, 0, 0, f"error {type(exc).__name__}", 0.0))
                    continue
                print(f"{key}: {wire / 1000:.0f} kB in {ms:.0f} ms", file=sys.stderr)
                sizes.append(OpSize(page, op.name, raw, wire, encoding, round(ms, 1)))
    return sizes


def render(sizes: list[OpSize], rtt_ms: float, mbit: float) -> str:
    lines = [
        f"Link model: {rtt_ms:.0f} ms round trip, {mbit:g} Mbit/s down (bytes at link speed "
        "plus one round trip per request; operations in parallel share the link).",
        "",
        "| Page | Operation | Raw | On the wire | Encoding | Warm server ms |",
        "|---|---|---|---|---|---|",
    ]
    pages = dict.fromkeys(s.page for s in sizes)
    for page in pages:
        rows = [s for s in sizes if s.page == page]
        for s in rows:
            lines.append(
                f"| {page} | {s.op} | {s.raw_bytes / 1000:.1f} kB | {s.wire_bytes / 1000:.1f} kB "
                f"| {s.encoding or 'none'} | {s.warm_ms:.0f} |"
            )
        wire = sum(s.wire_bytes for s in rows)
        est = rtt_ms / 1000 * 2 + wire * 8 / (mbit * 1_000_000)
        lines.append(f"| **{page}** | total | | **{wire / 1000:.1f} kB** | | link ~{est:.1f} s |")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--url", required=True, help="a spare API, e.g. http://127.0.0.1:8011")
    p.add_argument("--rtt-ms", type=float, default=280.0)
    p.add_argument("--mbit", type=float, default=10.0)
    args = p.parse_args(argv)
    sizes = asyncio.run(run(args.url))
    load.OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = load.OUT_DIR / "payload-sizes.json"
    out.write_text(json.dumps([asdict(s) for s in sizes], indent=2))
    print(render(sizes, args.rtt_ms, args.mbit))
    print(f"\nwritten {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
