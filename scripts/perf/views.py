"""The web app's VIEWS (route + search params + tab / disclosure state), found statically, and the
views file `benchmarks/api_latency_views.json` the crawler fills and `api_latency.py --view` reads.

A view is what a user can look at: a route, the search values it takes (`/edges?edge={edge}`:
`{edge}` is a placeholder the crawler fills with a real id from the clone), and the clicks that
reach a sub-view (a tab of the edge page, an opened section). `enumerate_views` derives them from
the source with `web_page_ops.py`'s import walk:

- one view per page route (pattern ids `:id`), its expected operations (on-load and uncertain,
  the shell's removed) and the operations only an interaction sends (`interaction`);
- one view per literal value a route's `validateSearch` accepts (`/edges?view=mine`) and one per
  id-valued search param (`/edges?edge={edge}`, `/explore?sel={instrument}`);
- one view per tab of every `<Tabs>` / `<TabStrip>` the route's page reaches (the tab's own
  operations: those of the component the tab id shows), attached to the first id-valued variant
  when the route has one (the tabs of an edge's page exist only with an edge chosen), and one per
  `<Disclosure>` / `<ExpandableRow>` with a literal label.

Limits: a tab that shows its content through a prop or a registry has no operations listed
(`target: false`); controls with computed names (help buttons, chips, segmented options) are not
static: the crawler discovers them at run time and adds them as `source: "discovered"` views.
Pure: no server, no store, no browser.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path

import web_page_ops as wpo

VIEWS_FILE = Path(__file__).resolve().parents[2] / "benchmarks/api_latency_views.json"
SEP = " > "
SHELL_ID = "(shell)"
# search param name -> the kind of real id the crawler picks from the clone
PICK_PARAMS = {
    "edge": "edge",
    "sel": "instrument",
    "symbol": "instrument",
    "ticker": "instrument",
    "screener": "screener",
    "run": "run",
    "session": "session",
}
# a `$param` route segment: the kind by the route's first segment (else the crawler scrapes a link)
PARAM_KINDS = {"edges": "edge", "screeners": "screener", "explore": "instrument", "runs": "run"}
TABS_RE = re.compile(r"<(?:Tabs|TabStrip|NavTabs)\b")
OPEN_RE = re.compile(r"<(?:Disclosure|ExpandableRow)\b")
ARRAY_RE = re.compile(r"^(?:export\s+)?const\s+(\w+)\b[^=\n]*=\s*\[", re.M)


class SelectionError(ValueError):
    """A view id the views file does not know, or one with nothing to measure."""


def pattern_id(path: str) -> str:
    """``/edges/$id/edit`` -> ``/edges/:id/edit``."""
    return re.sub(r"\$(\w*)", lambda m: ":" + (m.group(1) or "splat"), path)


def view_id(route: str, search: dict[str, str], clicks: list[dict]) -> str:
    """The stable id: pattern, ``?k=v`` search, then `` > kind:group:name`` per click."""
    out = pattern_id(route)
    if search:
        out += "?" + "&".join(f"{k}={v}" for k, v in sorted(search.items()))
    for c in clicks:
        out += SEP + ":".join(p for p in (c["kind"], c.get("group", ""), c["name"]) if p)
    return out


def _array_items(text: str, name: str) -> list[dict[str, str]]:
    """``{ id: 'a', label: 'A' }`` entries of the array constant ``name`` in ``text``."""
    for m in ARRAY_RE.finditer(text):
        if m.group(1) != name:
            continue
        body = text[m.end() - 1 : wpo.match_close(text, m.end() - 1) + 1]
        return [
            {"id": i, "label": label}
            for i, label in re.findall(r"id:\s*'([^']+)'\s*,\s*label:\s*'([^']*)'", body)
        ]
    return []


def _tab_controls(text: str) -> list[dict]:
    """The tabs of every ``<Tabs items={X} label="G">`` in ``text``."""
    found: list[dict] = []
    for m in TABS_RE.finditer(text):
        tag = text[m.start() : m.start() + 700]
        items = re.search(r"items=\{(\w+)", tag)
        label = re.search(r"\blabel=\"([^\"]*)\"", tag)
        if not items:
            continue
        for item in _array_items(text, items.group(1)):
            found.append(
                {
                    "kind": "tab",
                    "group": label.group(1) if label else "",
                    "name": item["label"],
                    "id": item["id"],
                }
            )
    return found


def _open_controls(text: str) -> list[dict]:
    """The ``<Disclosure label="x">`` / ``<ExpandableRow title="x">`` with a literal name."""
    found: list[dict] = []
    for m in OPEN_RE.finditer(text):
        tag = text[m.start() : m.start() + 400]
        name = re.search(r"\b(?:label|title)=\"([^\"]+)\"", tag)
        if name:
            found.append({"kind": "expand", "group": "", "name": name.group(1)})
    return found


def tab_targets(texts: list[tuple[Path, str]], tab_id: str) -> list[tuple[Path, str]]:
    """The (module, component) a tab id shows: ``=== 'id' && <X``, ``=== 'id' ? <X`` or
    ``case 'id': return <X``."""
    pats = [
        rf"===\s*'{re.escape(tab_id)}'\s*(?:&&|\?)\s*\(?\s*<(\w+)",
        rf"case\s+'{re.escape(tab_id)}'\s*:\s*return\s*\(?\s*<(\w+)",
    ]
    return [(p, c) for p, text in texts for pat in pats for c in re.findall(pat, text)]


def _literals(text: str, spec: str) -> list[str]:
    """String values of ``spec``: an inline ``['a', 'b']`` or the name of an array constant."""
    if spec.lstrip().startswith("["):
        return re.findall(r"'([^']+)'", spec)
    for arr in ARRAY_RE.finditer(text):
        if arr.group(1) == spec.strip():
            body = text[arr.end() - 1 : wpo.match_close(text, arr.end() - 1) + 1]
            return re.findall(r"'([^']+)'", body)
    return []


ONE_OF_RE = re.compile(r"\boneOf\(\s*(\[[^\]]*\](?:\s*as const)?|\w+)\s*,\s*raw\['(\w+)'\]")


def search_params(source: wpo.Source, route: wpo.Route) -> tuple[dict[str, list[str]], list[str]]:
    """({param: literal values} the route's validator accepts, [string-valued params]).

    Three shapes are read: ``typeof x === 'string'`` with ``VIEWS.find((v) => v === x)``,
    ``text(raw['x'])`` and ``oneOf(CONST | [..], raw['x'])``."""
    if route.validator is None:
        return {}, []
    path, name = route.validator
    m = source.module(path)
    span = m.decls.get(name)
    body = m.text[span[0] : span[1]] if span else ""
    strings = [
        *re.findall(r"typeof\s+(\w+)\s*===\s*'string'", body),
        *re.findall(r"\btext\(\s*raw\['(\w+)'\]", body),
    ]
    enums: dict[str, list[str]] = {}
    for spec, param in ONE_OF_RE.findall(body):
        if values := _literals(m.text, spec):
            enums[param] = values
    for arr in ARRAY_RE.finditer(m.text):
        values = re.findall(
            r"'([^']+)'", m.text[arr.end() - 1 : wpo.match_close(m.text, arr.end() - 1) + 1]
        )
        use = re.search(
            rf"\b{arr.group(1)}\.(?:find|some|includes)\(\(?\w*\)?\s*(?:=>\s*\w+\s*===\s*)?(\w+)\)",
            body,
        )
        if values and use:
            enums[use.group(1)] = values
    return enums, list(dict.fromkeys(strings))


def _reach_texts(walk: wpo.Walk, roots: list[wpo.Node]) -> list[tuple[Path, str]]:
    """The source text of every module a route's page reaches (each once)."""
    seen: dict[Path, str] = {}
    for path, _ in walk.reach([(n, wpo.LOAD) for n in roots]):
        seen.setdefault(path, walk.source.module(path).text)
    return list(seen.items())


def _ops_of(walk: wpo.Walk, nodes: list[wpo.Node]) -> dict[str, int]:
    return walk.classify([(n, wpo.LOAD) for n in nodes])


def _view(route: str, search: dict[str, str], clicks: list[dict], **fields: object) -> dict:
    segs = [s for s in route.strip("/").split("/") if s.startswith("$")]
    params = {
        (s[1:] or "splat"): PARAM_KINDS.get(route.strip("/").split("/")[0], "link") for s in segs
    }
    return {
        "route": pattern_id(route),
        "search": search,
        "clicks": clicks,
        "params": params,
        "ops": [],
        "uncertain": [],
        "interaction": [],
        "source": "static",
        **fields,
    }


def enumerate_views(src: Path) -> dict[str, dict]:
    """View id -> view, for every page route of the web source."""
    source = wpo.Source(src)
    routes = [r for r in wpo.enumerate_routes(src, source) if r.kind == "page" and r.pages]
    walk = wpo.Walk(source)
    static, shell = wpo.static_page_ops(src, routes)
    views: dict[str, dict] = {}
    # the shell (top bar, status strip, guards) sends its reads on every page: one view of its own
    views[SHELL_ID] = _view(
        "/ideas",
        {},
        [],
        ops=sorted(o for o, k in shell.items() if k != wpo.HANDLER),
        uncertain=sorted(o for o, k in shell.items() if k == wpo.MAYBE),
        interaction=sorted(o for o, k in shell.items() if k == wpo.HANDLER),
        shell=True,
    )
    for route in routes:
        ops = static[route.path]
        expected = {o for o, k in ops.items() if k != wpo.HANDLER}
        enums, strings = search_params(source, route)
        base = _view(
            route.path,
            {},
            [],
            ops=sorted(expected),
            uncertain=sorted(o for o, k in ops.items() if k == wpo.MAYBE),
            interaction=sorted(o for o, k in ops.items() if k == wpo.HANDLER),
        )
        views[view_id(route.path, {}, [])] = base
        anchor = base
        picks = [p for p in strings if p in PICK_PARAMS]
        for param in picks:
            search = {param: "{" + PICK_PARAMS[param] + "}"}
            variant = _view(route.path, search, [], ops=base["ops"], uncertain=base["uncertain"])
            views[view_id(route.path, search, [])] = variant
        if picks:
            anchor = views[view_id(route.path, {picks[0]: "{" + PICK_PARAMS[picks[0]] + "}"}, [])]
        for param, values in enums.items():
            if param == "tab":
                continue  # the tab clicks below are these views
            for value in values:
                search = {param: value}
                views[view_id(route.path, search, [])] = _view(
                    route.path, search, [], ops=base["ops"], uncertain=base["uncertain"]
                )
        texts = _reach_texts(walk, route.pages)
        taken = {o for o, k in ops.items() if k == wpo.LOAD} | set(shell)
        for ctl in _controls(texts):
            clicks = [{k: v for k, v in ctl.items() if k != "id"}]
            vid = view_id(route.path, anchor["search"], clicks)
            if vid in views:
                continue
            extra: dict[str, object] = {}
            if ctl["kind"] == "tab":
                found = [
                    n
                    for p, c in tab_targets(texts, ctl["id"])
                    if (n := walk._target(source.module(p), c))
                ]
                tab_ops = {o: k for o, k in _ops_of(walk, found).items() if o not in taken}
                extra = {
                    "ops": sorted(o for o, k in tab_ops.items() if k != wpo.HANDLER),
                    "uncertain": sorted(o for o, k in tab_ops.items() if k == wpo.MAYBE),
                    "interaction": sorted(o for o, k in tab_ops.items() if k == wpo.HANDLER),
                    "target": bool(found),
                }
            views[vid] = _view(
                route.path,
                anchor["search"],
                clicks,
                parent=view_id(route.path, anchor["search"], []),
                **extra,
            )
    return dict(sorted(views.items()))


def _controls(texts: list[tuple[Path, str]]) -> list[dict]:
    seen: set[tuple[str, str, str]] = set()
    out: list[dict] = []
    for _, text in texts:
        for ctl in [*_tab_controls(text), *_open_controls(text)]:
            key = (ctl["kind"], ctl["group"], ctl["name"])
            if key not in seen:
                seen.add(key)
                out.append(ctl)
    return out


# ---- the views file ---------------------------------------------------------------------------


def merge_static(existing: dict, static: dict[str, dict]) -> dict[str, dict]:
    """The static views, each keeping the ``captured`` result already in the file; views the
    crawler discovered stay (their static fields are theirs)."""
    old = existing.get("views", {})
    merged = {
        vid: {**v, **({"captured": old[vid]["captured"]} if "captured" in old.get(vid, {}) else {})}
        for vid, v in static.items()
    }
    for vid, v in old.items():
        if vid not in merged and v.get("source") == "discovered":
            merged[vid] = v
    return dict(sorted(merged.items()))


def load_views(path: Path = VIEWS_FILE) -> dict:
    """The views file (``{"views": {}}`` when it does not exist yet)."""
    return json.loads(path.read_text()) if path.is_file() else {"views": {}}


def save_views(views: dict[str, dict], path: Path = VIEWS_FILE) -> None:
    doc = {"generated": f"{datetime.now(UTC):%Y-%m-%d %H:%M UTC}", "views": views}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=1) + "\n")


def captured_requests(view: dict) -> list[dict]:
    """The GraphQL requests the crawler recorded for one view."""
    return (view.get("captured") or {}).get("requests", [])


def op_key(name: str, vid: str) -> str:
    """The key a view's operation is measured under: operation x view, so a second view never
    replays the first view's variables."""
    return f"{name} [{vid}]"


def view_operations(
    doc: dict, view_ids: list[str], known: dict[str, dict]
) -> tuple[dict[str, dict], dict[str, list[str]]]:
    """({op_key: {query, variables}}, {view id: its op keys}) for the views.

    A captured view gives the documents and variables the browser sent for it (the first request
    of each operation); a view the crawler has not visited falls back to its static operations,
    with the documents of ``known``. An id the file does not hold, or a view with no operation
    at all, is a ``SelectionError``."""
    views = doc.get("views", {})
    ops: dict[str, dict] = {}
    by_view: dict[str, list[str]] = {}
    for vid in view_ids:
        if vid not in views:
            raise SelectionError(
                f"--view {vid}: not in the views file (known: {sorted(views)[:8]}...)"
            )
        keys: list[str] = []
        for req in captured_requests(views[vid]):
            key = op_key(req["op"], vid)
            if key not in ops:
                ops[key] = {"query": req["query"], "variables": req["variables"]}
                keys.append(key)
        if not keys:
            for name in views[vid].get("ops", []):
                if name not in known:
                    raise SelectionError(f"--view {vid}: operation {name} has no captured document")
                ops[op_key(name, vid)] = known[name]
                keys.append(op_key(name, vid))
        if not keys:
            raise SelectionError(f"--view {vid}: no operation (not captured, none expected)")
        by_view[vid] = keys
    return ops, by_view
