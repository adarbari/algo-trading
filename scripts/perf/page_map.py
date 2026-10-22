"""The per-route page map of the uncached latency run (`scripts/perf/api_latency.py`).

Requests per operation per route from the capture, each route's calls and shares of the page's
time, and the static import-walk map set against the capture (`web_page_ops.py`). Pure: no
server, no store."""

from __future__ import annotations

import web_page_ops as wpo


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
