#!/usr/bin/env python3
"""Enforce single ownership of responsibilities (ADR 0019), with a shrink-only ratchet.

``architecture/ownership.toml`` names, for each responsibility, the modules that own it and
AST patterns that signal someone else doing the same work (a ``latest_date`` call, a
``RunRecord`` built, ``os.environ`` read, ``urllib.request`` imported…). This script scans
``src/`` and ``apps/`` and reports every hit outside the owner's modules.

``architecture/known_violations.toml`` lists today's hits (file + responsibility + count).
- a hit that is not listed (or a count above the listed one) fails: extend the owner instead;
- a listed count above what is found fails too: lower or remove the entry, so the list only
  ever shrinks. ``--update`` rewrites the file with current counts, and refuses to grow it.

Usage: python scripts/check_ownership.py [--root DIR] [--update] [--summary]
Stdlib only, so it runs before (and without) the project environment.
"""

from __future__ import annotations

import argparse
import ast
import fnmatch
import re
import sys
import tomllib
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

REGISTRY = Path("architecture/ownership.toml")
KNOWN = Path("architecture/known_violations.toml")
SCAN_ROOTS = ("src", "apps")
RULE_KINDS = ("call", "call_regex", "attr", "import", "string", "string_prefix")


@dataclass(frozen=True)
class Rule:
    kind: str
    value: str
    arg: str | None = None  # call only: a string-literal argument that must be present
    exclude: tuple[str, ...] = ()  # import only: module prefixes that are fine

    def describe(self) -> str:
        return f"{self.kind} {self.value!r}" + (f" with {self.arg!r}" if self.arg else "")


@dataclass(frozen=True)
class Responsibility:
    id: str
    owner: tuple[str, ...]
    allowed: tuple[str, ...]  # owner + target_owner + allowed: where a hit is not a violation
    section: str
    rules: tuple[Rule, ...]

    def permits(self, path: str) -> bool:
        return any(fnmatch.fnmatch(path, pattern) for pattern in self.allowed)


@dataclass(frozen=True)
class Hit:
    path: str
    line: int
    responsibility: str
    rule: Rule


def load_registry(root: Path) -> list[Responsibility]:
    data = tomllib.loads((root / REGISTRY).read_text())
    out = []
    for entry in data["responsibility"]:
        rules = []
        for spec in entry.get("detect", []):
            kinds = [k for k in RULE_KINDS if k in spec]
            if len(kinds) != 1:
                raise ValueError(
                    f"{entry['id']}: each detect rule needs exactly one of {RULE_KINDS}"
                )
            rules.append(
                Rule(kinds[0], spec[kinds[0]], spec.get("arg"), tuple(spec.get("except", ())))
            )
        owner = tuple(entry["owner"])
        allowed = owner + tuple(entry.get("target_owner", ())) + tuple(entry.get("allowed", ()))
        out.append(Responsibility(entry["id"], owner, allowed, entry["section"], tuple(rules)))
    return out


def dotted(node: ast.AST) -> str:
    """``a.b.c`` for names and attribute chains; ``?`` stands in for anything else."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return f"{dotted(node.value)}.{node.attr}"
    return "?"


def matches_name(name: str, pattern: str) -> bool:
    return name == pattern or name.endswith("." + pattern)


def docstring_nodes(tree: ast.AST) -> set[int]:
    ids = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                ids.add(id(body[0].value))
    return ids


def string_args(call: ast.Call) -> set[str]:
    values = [*call.args, *(k.value for k in call.keywords)]
    return {v.value for v in values if isinstance(v, ast.Constant) and isinstance(v.value, str)}


def rule_hits(rule: Rule, node: ast.AST, docstrings: set[int]) -> bool:
    kind, value = rule.kind, rule.value
    if kind in ("call", "call_regex") and isinstance(node, ast.Call):
        name = dotted(node.func)
        found = matches_name(name, value) if kind == "call" else re.search(value, name)
        return bool(found) and (rule.arg is None or rule.arg in string_args(node))
    if kind == "attr" and isinstance(node, ast.Attribute):
        return matches_name(dotted(node), value)
    if kind == "import" and isinstance(node, ast.Import | ast.ImportFrom):
        modules = (
            [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or ""]
        )
        return any(
            (m == value or m.startswith(value + "."))
            and not any(m.startswith(e) for e in rule.exclude)
            for m in modules
        )
    if kind in ("string", "string_prefix") and isinstance(node, ast.Constant):
        if not isinstance(node.value, str) or id(node) in docstrings:
            return False
        return node.value == value if kind == "string" else node.value.startswith(value)
    return False


def scan_file(path: Path, rel: str, registry: list[Responsibility]) -> list[Hit]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=rel)
    docstrings = docstring_nodes(tree)
    hits = []
    for node in ast.walk(tree):
        for resp in registry:
            for rule in resp.rules:
                if rule_hits(rule, node, docstrings):
                    hits.append(Hit(rel, getattr(node, "lineno", 0), resp.id, rule))
    return hits


def scan(root: Path, registry: list[Responsibility]) -> list[Hit]:
    """Every detect hit outside its responsibility's allowed modules."""
    by_id = {r.id: r for r in registry}
    hits = []
    for top in SCAN_ROOTS:
        for path in sorted((root / top).rglob("*.py")):
            if {".venv", "node_modules"} & set(path.parts):
                continue  # vendored dependencies (apps/web/node_modules), not our code
            rel = path.relative_to(root).as_posix()
            hits += [
                h
                for h in scan_file(path, rel, registry)
                if not by_id[h.responsibility].permits(rel)
            ]
    return sorted(hits, key=lambda h: (h.path, h.line, h.responsibility))


def load_known(root: Path) -> Counter[tuple[str, str]]:
    path = root / KNOWN
    if not path.exists():
        return Counter()
    data = tomllib.loads(path.read_text())
    return Counter(
        {(v["file"], v["responsibility"]): int(v["count"]) for v in data.get("violation", [])}
    )


def write_known(root: Path, counts: Counter[tuple[str, str]]) -> None:
    lines = [
        "# Ratchet for scripts/check_ownership.py (ADR 0019): ownership violations, one entry per",
        "# file doing work another module owns. EMPTY since restructure PR 6, and a fitness test",
        "# keeps it empty: extend the owner named in architecture/ownership.toml instead. A real",
        "# exception needs an ADR and goes in that responsibility's `allowed` list, with why.",
        "",
    ]
    for (file, resp), count in sorted(counts.items(), key=lambda kv: (kv[0][1], kv[0][0])):
        lines += [
            "[[violation]]",
            f'responsibility = "{resp}"',
            f'file = "{file}"',
            f"count = {count}",
            "",
        ]
    (root / KNOWN).write_text("\n".join(lines))


def compare(
    hits: list[Hit], known: Counter[tuple[str, str]], registry: list[Responsibility]
) -> tuple[list[str], list[str]]:
    """-> (new-violation messages, stale-allowlist messages)."""
    by_id = {r.id: r for r in registry}
    found = Counter((h.path, h.responsibility) for h in hits)
    new, stale = [], []
    for key, count in sorted(found.items()):
        if count > known.get(key, 0):
            resp = by_id[key[1]]
            lines = [
                f"  {h.path}:{h.line}  {h.rule.describe()}"
                for h in hits
                if (h.path, h.responsibility) == key
            ]
            new.append(
                f"[{resp.id}] {key[0]}: {count} hit(s), {known.get(key, 0)} allowed\n"
                + "\n".join(lines)
                + f"\n  owner: {', '.join(resp.owner)}\n  see: {resp.section}"
            )
    for key, count in sorted(known.items()):
        if found.get(key, 0) < count:
            stale.append(
                f"[{key[1]}] {key[0]}: listed {count}, found {found.get(key, 0)}; "
                f"lower or remove it from {KNOWN} (`make ownership-update`)"
            )
    unknown = sorted({resp for _, resp in known} - set(by_id))
    stale += [
        f"[{resp}] is not a responsibility in {REGISTRY}; remove its entries" for resp in unknown
    ]
    return new, stale


def summary(hits: list[Hit]) -> str:
    counts = Counter(h.responsibility for h in hits)
    files = Counter(resp for _, resp in {(h.path, h.responsibility) for h in hits})
    rows = [
        f"  {resp:<24} {counts[resp]:>4} hits in {files[resp]:>3} files" for resp in sorted(counts)
    ]
    return "ownership violations (the restructure to-do list):\n" + "\n".join(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--update", action="store_true", help="shrink the ratchet to current counts"
    )
    parser.add_argument("--summary", action="store_true", help="print counts per responsibility")
    args = parser.parse_args(argv)
    registry = load_registry(args.root)
    hits = scan(args.root, registry)
    new, stale = compare(hits, load_known(args.root), registry)
    if args.summary:
        print(summary(hits))
    if new:
        print(
            "NEW ownership violations: extend the owner instead of re-implementing it (ADR 0019)."
        )
        print("A new responsibility needs an entry + owner in architecture/ownership.toml.\n")
        print("\n\n".join(new))
        return 1
    if args.update:
        write_known(args.root, Counter((h.path, h.responsibility) for h in hits))
        print(f"{KNOWN} updated ({len(hits)} known hits).")
        return 0
    if stale:
        print("Stale entries in the ownership ratchet (good news: something was fixed):\n")
        print("\n".join(stale))
        return 1
    print(
        f"ownership: OK ({len(registry)} responsibilities, {len(hits)} known violations remaining)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
