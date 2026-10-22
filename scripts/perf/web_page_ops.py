"""The web app's pages and the GraphQL operations each one sends, found statically (no browser).

Used by `api_latency.py --uncached` to cross-check the runtime capture (`api_latency_pages.json`).
Two parts, both regex based over the TypeScript source (formatted by prettier: declarations start
in column 0), no TypeScript toolchain:

1. `enumerate_routes`: every leaf route of the TanStack route tree under `src/app/routes`
   (`createRoute` blocks, route factories such as `ingestionRoute(adminRoute)`, and
   `placeholderRoute(...)` calls) with its full path pattern, the page component it renders
   (resolved to the module and export a `lazyPage` / import names) and the page module's
   `prefetch...Reads` its loader calls.
2. `walk`: a symbol graph (a declaration -> the declarations and imports its body names, barrels
   `export { X } from` followed to the defining file) down to the `graphql(` query documents.
   Each reference is `load` (rendered or called unconditionally), `maybe` (behind `&&` / `?`,
   an `enabled` option, or a hook that gates itself with `enabled`) or `handler` (inside an
   arrow function: an event handler, a callback). An operation's class is the best path to it:
   on-load, uncertain, or interaction-only. The shell (WorkspaceLayout, GuideLayout, the route
   guards) is walked once and its operations are separated from every page's.

Limits (the generated doc says so): a reference through a prop, a context or a registry is not
seen; a conditional the regex cannot read counts as on-load; an operation sent by a hook inside
`useMemo` / `useEffect` is on-load here and `handler` if written inside an arrow.
"""

# ruff: noqa: PLR0911, PLR0912, PLR0915  (a source-text scanner: one pass with many cases)
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

LOAD, MAYBE, HANDLER = 0, 1, 2
CLASS_NAMES = {LOAD: "on-load", MAYBE: "uncertain", HANDLER: "interaction"}
SHELL_ROOTS = (
    ("app/layouts/WorkspaceLayout.tsx", "WorkspaceLayout"),
    ("app/layouts/GuideLayout.tsx", "GuideLayout"),
    ("app/workspaces/guard.ts", "workspaceGuard"),
    ("app/workspaces/guard.ts", "viewerGuard"),
)

IMPORT_RE = re.compile(
    r"^import\s+(?!type\b)(?:(\w+)\s*,?\s*)?(?:\{([^}]*)\}|\*\s+as\s+(\w+))?\s*from\s*['\"]([^'\"]+)['\"]",
    re.M,
)
REEXPORT_RE = re.compile(r"^export\s+(?!type\b)\{([^}]*)\}\s*from\s*['\"]([^'\"]+)['\"]", re.M)
STAR_RE = re.compile(r"^export\s+\*\s+from\s*['\"]([^'\"]+)['\"]", re.M)
LOCAL_EXPORT_RE = re.compile(r"^export\s+(?!type\b)\{([^}]*)\}\s*;?\s*$", re.M)
DECL_RE = re.compile(
    r"^(?:export\s+)?(?:default\s+)?(?:async\s+)?"
    r"(?:function\*?\s+(\w+)|(?:const|let|class)\s+(\w+))",
    re.M,
)
LAZY_RE = re.compile(
    r"(?:const|let)\s+(\w+)\s*=\s*lazyPage\(\s*"
    r"(?:\(\)\s*=>\s*import\(['\"]([^'\"]+)['\"]\)|(\w+))\s*,\s*['\"](\w+)['\"]"
)
THUNK_RE = re.compile(r"(?:const)\s+(\w+)\s*=\s*\(\)\s*=>\s*import\(['\"]([^'\"]+)['\"]\)")
DOC_RE = re.compile(r"graphql\(\s*`\s*(query|mutation|subscription)\s+(\w+)")
IDENT_RE = re.compile(r"(?<![.\w$])([A-Za-z_]\w*)\b")


def strip_comments(text: str) -> str:
    """The source without ``/* */`` and ``//`` comments (a ``//`` after ``:`` is a URL, kept)."""
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return re.sub(r"(?m)(^|[^:\w'\"`])//.*$", r"\1", text)


def match_close(text: str, open_at: int) -> int:
    """The index of the bracket closing the one at ``open_at`` (strings and templates skipped)."""
    pairs = {"(": ")", "{": "}", "[": "]"}
    stack: list[str] = []
    i = open_at
    while i < len(text):
        c = text[i]
        if c in "'\"`":
            j = i + 1
            while j < len(text) and text[j] != c:
                j += 2 if text[j] == "\\" else 1
            i = j
        elif c in pairs:
            stack.append(pairs[c])
        elif stack and c == stack[-1]:
            stack.pop()
            if not stack:
                return i
        i += 1
    return len(text) - 1


def resolve_module(spec: str, importer: Path, src: Path) -> Path | None:
    """The source file a ``@/x`` or relative import names (``None``: a package or not found)."""
    if spec.startswith("@/"):
        base = src / spec[2:]
    elif spec.startswith("."):
        base = (importer.parent / spec).resolve()
    else:
        return None
    for cand in (
        base,
        base.with_name(base.name + ".ts"),
        base.with_name(base.name + ".tsx"),
        base / "index.ts",
        base / "index.tsx",
    ):
        if cand.is_file():
            return cand
    return None


def _names(block: str) -> list[tuple[str, str]]:
    """``a, b as c`` -> [(imported, local)]; type-only members dropped."""
    out = []
    for raw in block.split(","):
        part = raw.strip()
        if not part or part.startswith("type "):
            continue
        imported, _, local = part.partition(" as ")
        out.append((imported.strip(), (local or imported).strip()))
    return out


@dataclass
class Module:
    """One parsed source file."""

    path: Path
    text: str
    imports: dict[str, tuple[Path, str]] = field(default_factory=dict)  # local -> (file, name)
    reexports: dict[str, tuple[Path, str]] = field(default_factory=dict)  # exported -> (file, name)
    stars: list[Path] = field(default_factory=list)
    decls: dict[str, tuple[int, int]] = field(default_factory=dict)  # name -> body span
    local_exports: dict[str, str] = field(default_factory=dict)  # exported -> local
    docs: dict[str, tuple[str, str]] = field(default_factory=dict)  # decl -> (kind, op name)
    lazies: dict[str, tuple[Path, str]] = field(default_factory=dict)  # local -> (file, export)
    namespaces: dict[str, Path] = field(default_factory=dict)


class Source:
    """The parsed `src` tree, files parsed on first use."""

    def __init__(self, src: Path) -> None:
        self.src = src
        self._modules: dict[Path, Module] = {}

    def module(self, path: Path) -> Module:
        path = path.resolve()
        if path not in self._modules:
            self._modules[path] = self._parse(path)
        return self._modules[path]

    def _parse(self, path: Path) -> Module:
        text = strip_comments(path.read_text())
        m = Module(path, text)
        for default, named, star, spec in IMPORT_RE.findall(text):
            target = resolve_module(spec, path, self.src)
            if target is None:
                continue
            if star:
                m.namespaces[star] = target
            if default:
                m.imports[default] = (target, "default")
            for imported, local in _names(named):
                m.imports[local] = (target, imported)
        for block, spec in REEXPORT_RE.findall(text):
            target = resolve_module(spec, path, self.src)
            for imported, local in _names(block):
                if target is not None:
                    m.reexports[local] = (target, imported)
        for spec in STAR_RE.findall(text):
            target = resolve_module(spec, path, self.src)
            if target is not None:
                m.stars.append(target)
        for block in LOCAL_EXPORT_RE.findall(text):
            for imported, local in _names(block):
                m.local_exports[local] = imported
        starts = [(d.start(), d.group(1) or d.group(2)) for d in DECL_RE.finditer(text)]
        for i, (start, name) in enumerate(starts):
            end = starts[i + 1][0] if i + 1 < len(starts) else len(text)
            m.decls[name] = (start, end)
            doc = DOC_RE.search(text, start, end)
            if doc and text[start:end].lstrip().startswith(("const", "export const")):
                m.docs[name] = (doc.group(1), doc.group(2))
        thunks = dict(THUNK_RE.findall(text))
        for local, inline, thunk, export in LAZY_RE.findall(text):
            target = resolve_module(inline or thunks.get(thunk, ""), path, self.src)
            if target is not None:
                m.lazies[local] = (target, export)
        return m

    def resolve_export(
        self, path: Path, name: str, seen: frozenset = frozenset()
    ) -> tuple[Path, str] | None:
        """The (file, declaration) that ``name`` exported from ``path`` is defined in."""
        key = (path.resolve(), name)
        if key in seen:
            return None
        seen = seen | {key}
        m = self.module(path)
        local = m.local_exports.get(name, name)
        if local in m.decls and local not in m.imports:
            return m.path, local
        if name in m.reexports:
            target, imported = m.reexports[name]
            return self.resolve_export(target, imported, seen)
        if local in m.imports:  # `import { x }` then `export { x }`
            target, imported = m.imports[local]
            return self.resolve_export(target, imported, seen)
        if local in m.lazies:
            return m.path, local
        for star in m.stars:
            found = self.resolve_export(star, name, seen)
            if found:
                return found
        return None


# ---- references inside one declaration ------------------------------------------------------


def body_start(text: str) -> int:
    """Offset (in the declaration text) where its own body begins, so the declaration's own
    function brace is not counted as a nested arrow."""
    head = DECL_RE.match(text)
    if not head:
        return 0
    if head.group(1):  # function Name(params) {
        p = text.find("(", head.end())
        if p < 0:
            return 0
        q = text.find("{", match_close(text, p))
        return q + 1 if q >= 0 else 0
    arrow = text.find("=>", head.end())
    if arrow < 0:
        return 0
    rest = arrow + 2
    while rest < len(text) and text[rest] in " \n":
        rest += 1
    return rest + 1 if rest < len(text) and text[rest] in "{(" else rest


def reference_kinds(text: str) -> list[tuple[str, int]]:
    """Every ``(identifier, kind)`` named in a declaration's text, with ``LOAD`` / ``MAYBE`` /
    ``HANDLER`` by where it stands (see the module docstring)."""
    start = body_start(text)
    arrow_depth = 0
    stack: list[tuple[str, bool]] = []  # (closer, is_arrow_scope)
    pending_arrow = False
    out: list[tuple[str, int]] = []
    i = start
    n = len(text)
    while i < n:
        c = text[i]
        if c in "'\"`":
            j = i + 1
            while j < n and text[j] != c:
                j += 2 if text[j] == "\\" else 1
            i = j + 1
            continue
        if text.startswith("=>", i):
            pending_arrow = True
            i += 2
            nxt = i
            while nxt < n and text[nxt] in " \n":
                nxt += 1
            if nxt < n and text[nxt] not in "{(":  # expression body: ends at , ) ] } ;
                stack.append(("expr", True))
                arrow_depth += 1
                pending_arrow = False
            continue
        if c in "{([":
            stack.append(({"{": "}", "(": ")", "[": "]"}[c], pending_arrow))
            if pending_arrow:
                arrow_depth += 1
            pending_arrow = False
        elif c in "})]":
            while stack and stack[-1][0] == "expr":
                stack.pop()
                arrow_depth -= 1
            if stack:
                _, was_arrow = stack.pop()
                arrow_depth -= 1 if was_arrow else 0
        elif c in ",;":
            while stack and stack[-1][0] == "expr":
                stack.pop()
                arrow_depth -= 1
        else:
            m = IDENT_RE.match(text, i) if (c.isalpha() or c in "_") else None
            if m and (i == 0 or (text[i - 1] not in ".$" and not text[i - 1].isalnum())):
                name = m.group(1)
                kind = HANDLER if arrow_depth > 0 else LOAD
                if kind == LOAD and _conditional(text, i, m.end()):
                    kind = MAYBE
                out.append((name, kind))
                i = m.end()
                continue
        i += 1
    return out


def _conditional(text: str, at: int, end: int) -> bool:
    """A reference behind ``&&`` / ``||`` / ``?`` or called with an ``enabled`` option."""
    before = text[max(0, at - 80) : at].rstrip(" \n(<!")
    if before.endswith(("&&", "||", "?", "??")):
        return True
    if text[end : end + 1] == "(":
        return bool(re.search(r"\benabled\b", text[end : match_close(text, end)]))
    return False


# ---- the walk -------------------------------------------------------------------------------


Node = tuple[Path, str]


class Walk:
    """Operation classes reachable from root symbols."""

    def __init__(self, source: Source) -> None:
        self.source = source
        self._edges: dict[Node, list[tuple[Node, int]]] = {}

    def edges(self, node: Node) -> list[tuple[Node, int]]:
        if node not in self._edges:
            self._edges[node] = self._build(node)
        return self._edges[node]

    def _target(self, m: Module, name: str) -> Node | None:
        if name in m.lazies:
            target, export = m.lazies[name]
            return self.source.resolve_export(target, export)
        if name in m.decls and name not in m.imports:
            return m.path, name
        if name in m.imports:
            target, imported = m.imports[name]
            return self.source.resolve_export(target, imported)
        return None

    def _build(self, node: Node) -> list[tuple[Node, int]]:
        path, name = node
        m = self.source.module(path)
        span = m.decls.get(name)
        if span is None:
            return []
        text = m.text[span[0] : span[1]]
        best: dict[Node, int] = {}
        for ident, kind in reference_kinds(text):
            if ident == name:
                continue
            target = self._target(m, ident)
            if target is None:
                for ns, ns_path in m.namespaces.items():  # `ns.member`
                    if ident == ns:
                        for member in re.findall(rf"\b{ns}\.(\w+)", text):
                            found = self.source.resolve_export(ns_path, member)
                            if found:
                                best[found] = min(best.get(found, HANDLER), kind)
                continue
            tm = self.source.module(target[0])
            edge = kind
            if target[1] in tm.docs:
                edge = LOAD  # a document is read by the hook's own queryFn, an arrow by design
            elif self._gates_itself(target) and kind == LOAD:
                edge = MAYBE
            best[target] = min(best.get(target, HANDLER), edge)
        return list(best.items())

    def _gates_itself(self, node: Node) -> bool:
        """A hook that takes ``enabled`` (its read may not start): its callers are uncertain."""
        m = self.source.module(node[0])
        span = m.decls.get(node[1])
        return bool(
            span
            and node[1].startswith("use")
            and re.search(r"\benabled\b", m.text[span[0] : span[1]])
        )

    def classify(self, roots: list[tuple[Node, int]]) -> dict[str, int]:
        """Operation name -> best (lowest) class over every path from the roots."""
        best: dict[Node, int] = {}
        work = list(roots)
        while work:
            node, kind = work.pop()
            if best.get(node, 3) <= kind:
                continue
            best[node] = kind
            for target, edge in self.edges(node):
                work.append((target, max(kind, edge)))
        ops: dict[str, int] = {}
        for (path, name), kind in best.items():
            doc = self.source.module(path).docs.get(name)
            if doc and doc[0] == "query":
                ops[doc[1]] = min(ops.get(doc[1], 3), kind)
        return ops


def all_query_ops(src: Path) -> set[str]:
    """Every query operation document declared in the source (tests and generated files apart)."""
    found: set[str] = set()
    for f in src.rglob("*.ts*"):
        rel = f.relative_to(src).as_posix()
        if ".test." in rel or "/generated/" in rel or ".stories." in rel:
            continue
        for kind, name in DOC_RE.findall(strip_comments(f.read_text())):
            if kind == "query":
                found.add(name)
    return found


# ---- routes ---------------------------------------------------------------------------------

CREATE_RE = re.compile(r"(?:(?:export\s+)?const\s+(\w+)\s*=\s*|return\s+)?createRoute\(\{")
PLACEHOLDER_RE = re.compile(r"placeholderRoute\((\w+),\s*\w+,\s*'([^']*)',\s*'([^']*)'\)")


@dataclass
class Route:
    """One route of the tree: its pattern and the page it renders."""

    path: str  # the full pattern, e.g. /screeners/$id
    pages: list[Node] = field(default_factory=list)  # page component symbols
    prefetch: list[Node] = field(default_factory=list)
    search: bool = False  # declares search params (validateSearch)
    file: str = ""
    kind: str = "page"  # page | placeholder | redirect | layout


@dataclass
class _Raw:
    var: str | None
    seg: str | None
    pathless: bool
    parent: str | None
    block: str
    file: Path
    local_text: str
    placeholder: bool = False


def _join(*segments: str | None) -> str:
    parts = [s.strip("/") for s in segments if s and s.strip("/")]
    return "/" + "/".join(parts)


def _field(block: str, key: str) -> str | None:
    m = re.search(rf"\b{key}:\s*'([^']*)'", block)
    return m.group(1) if m else None


def enumerate_routes(src: Path, source: Source | None = None) -> list[Route]:
    """Every leaf route under ``src/app/routes`` with its full path and page symbols."""
    source = source or Source(src)
    files = sorted((src / "app" / "routes").rglob("*.ts*"))
    files = [f for f in files if ".test." not in f.name]
    raws: list[_Raw] = []
    factories: dict[str, _Raw] = {}
    for f in files:
        text = strip_comments(f.read_text())
        for m in CREATE_RE.finditer(text):
            open_at = text.index("{", m.end() - 2)
            block = text[open_at : match_close(text, open_at) + 1]
            parent = re.search(r"getParentRoute:\s*\(\)\s*=>\s*(\w+)", block)
            seg = _field(block, "path")
            raw = _Raw(
                m.group(1), seg, seg is None, parent.group(1) if parent else None, block, f, text
            )
            head = text[max(0, m.start() - 500) : m.start()]
            factory = re.findall(r"function\s+(\w+)\s*(?:<[^>]*>)?\s*\(\s*parent\b", head)
            if m.group(1) is None and factory:
                factories[factory[-1]] = raw
            else:
                raws.append(raw)
        for ph in PLACEHOLDER_RE.finditer(text):
            raws.append(_Raw(None, ph.group(3), False, ph.group(1), "", f, text, placeholder=True))
    for f in files:  # factory call sites: `ingestionRoute(adminRoute)`
        text = strip_comments(f.read_text())
        for name, template in factories.items():
            for call in re.finditer(rf"(?<!function )\b{name}\((\w+)\)", text):
                raws.append(
                    _Raw(
                        None,
                        template.seg,
                        template.pathless,
                        call.group(1),
                        template.block,
                        template.file,
                        template.local_text,
                    )
                )
    local = {(r.file, r.var): r for r in raws if r.var}
    anywhere = {r.var: r for r in raws if r.var}

    def parent_of(r: _Raw) -> _Raw | None:
        """The parent's block: a name in the same file first, else the one it imports."""
        key = (r.file, r.parent)
        return local.get(key) or anywhere.get(r.parent or "")

    has_child = {id(p) for r in raws if (p := parent_of(r)) is not None}

    def full(r: _Raw) -> str:
        segs: list[str | None] = []
        cur: _Raw | None = r
        while cur is not None:
            segs.append(cur.seg)
            cur = parent_of(cur)
        return _join(*reversed(segs))

    routes: list[Route] = []
    for r in raws:
        if id(r) in has_child and not r.placeholder:
            continue  # a layout: only its leaves are pages
        route = Route(
            full(r), file=r.file.relative_to(src).as_posix(), search="validateSearch" in r.block
        )
        if r.placeholder:
            route.kind = "placeholder"
        else:
            _page_symbols(source, r, route)
            if not route.pages:
                route.kind = "redirect" if "redirect(" in r.block else "layout"
        routes.append(route)
    return sorted({rt.path: rt for rt in routes}.values(), key=lambda rt: rt.path)


def _page_symbols(source: Source, r: _Raw, route: Route) -> None:
    """The page component symbols and `prefetch...Reads` of one route block."""
    m = source.module(r.file)
    names = re.findall(r"pageRoute\((\w+)", r.block) + re.findall(r"\b\w+Loading\((\w+)\)", r.block)
    comp = re.search(r"\bcomponent:\s*(\w+)", r.block)
    candidates = list(names)
    if comp:
        candidates.append(comp.group(1))
        span = m.decls.get(comp.group(1))
        if span and comp.group(1) not in m.lazies:  # a local wrapper: the pages it renders
            candidates += re.findall(r"<([A-Z]\w*)", m.text[span[0] : span[1]])
    candidates += re.findall(r"<([A-Z]\w*)", r.block)
    walk = Walk(source)
    for name in dict.fromkeys(candidates):
        if name in m.lazies or name in m.imports:
            node = walk._target(m, name)
            if node and node not in route.pages and "app/layouts" not in node[0].as_posix():
                route.pages.append(node)
    modules = [
        (m.lazies[n][0] if n in m.lazies else m.imports[n][0])
        for n in dict.fromkeys(candidates)
        if n in m.lazies or n in m.imports
    ]
    for prefetch in re.findall(r"\.(prefetch\w+)\(", r.block):
        for module in modules:
            found = source.resolve_export(module, prefetch)
            if found and found not in route.prefetch:
                route.prefetch.append(found)


# ---- matching a route pattern to a captured URL ---------------------------------------------


def pattern_regex(pattern: str) -> re.Pattern[str]:
    parts = [
        ("[^/]+" if s.startswith("$") else re.escape(s)) for s in pattern.strip("/").split("/") if s
    ]
    return re.compile("^/" + "/".join(parts) + "/?$")


def specificity(pattern: str) -> tuple[int, int]:
    segs = [s for s in pattern.strip("/").split("/") if s]
    return (sum(s.startswith("$") for s in segs), -len(segs))


def match_capture(routes: list[str], captured: list[str]) -> tuple[dict[str, list[str]], list[str]]:
    """Captured URLs per route pattern (the most specific match wins; the query string is kept
    off the match) and the URLs no route matches."""
    per: dict[str, list[str]] = {r: [] for r in routes}
    orphans: list[str] = []
    for url in captured:
        path = url.split("?")[0].split("#")[0]
        hits = [r for r in routes if pattern_regex(r).match(path)]
        if hits:
            per[min(hits, key=specificity)].append(url)
        else:
            orphans.append(url)
    return per, orphans


def static_page_ops(
    src: Path, routes: list[Route]
) -> tuple[dict[str, dict[str, int]], dict[str, int]]:
    """({route path: {op: class}} with the shell's ops removed, the shell's {op: class})."""
    source = Source(src)
    walk = Walk(source)
    shell_roots: list[tuple[Node, int]] = []
    for rel, name in SHELL_ROOTS:
        p = src / rel
        if p.is_file():
            found = source.resolve_export(p, name)
            if found:
                shell_roots.append((found, LOAD))
    shell = walk.classify(shell_roots)
    pages: dict[str, dict[str, int]] = {}
    for route in routes:
        roots = [(n, LOAD) for n in route.pages + route.prefetch]
        ops = walk.classify(roots)
        pages[route.path] = {o: k for o, k in ops.items() if o not in shell}
    return pages, shell
