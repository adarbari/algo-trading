#!/usr/bin/env python3
"""A git merge driver for the shared perf and latency JSON files, so merging main is mechanical.

Owner decision 2026-11-02: every Evening Desk UI PR touches ``apps/web/perf-budgets.json``,
``benchmarks/api_latency_views.json`` and ``benchmarks/api_latency_views.captured.json``, so each
merge to main made every open UI PR conflict again (five PRs, a merge and a 5-15 min pre-push
run each). Declared in ``.gitattributes``; registered per clone by
``scripts/ops/install_merge_drivers.sh``.

    merge_budgets.py budgets %O %A %B [%P]    perf-budgets.json
    merge_budgets.py views   %O %A %B [%P]    the two latency files

``%A`` (ours) is overwritten with the result; exit 0 = merged, 1 = conflict (a normal conflict
file, with markers, is left in ``%A``). ``budgets``: a three-way merge per leaf, keys unioned,
the larger number where both sides changed it, the ``reasons`` text of the winning number, and a
key one side removed stays removed, even where the other side raised it: the side that removed
a page or route removed what the budget measures, and a kept raise left a budget for a page that
is gone, or half an e2e entry (2026-11-02, #1035: twice; a removed budget the code still needs
fails `check-bundle-budgets` "a budget for every lazy page" instead, at the pre-push hook). A
reason whose budget no longer exists is dropped. ``views``: views unioned by key, the entry of
the side that changed it (ours when both did), so a captured document is never lost to a
regeneration. Unparsable JSON falls back to a normal conflict.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

Path_ = tuple[str, ...]
_SCALAR = r'(?:"(?:[^"\\]|\\.)*"|-?\d[\d.eE+-]*|true|false|null)'
_INLINE = re.compile(rf"\[\s+({_SCALAR}(?:,\s+{_SCALAR})*)\s+\]")
_GONE = object()


def flatten(tree: Any, prefix: Path_ = ()) -> dict[Path_, Any]:
    """Every leaf (a non-dict value) by its key path, in document order."""
    if not isinstance(tree, dict):
        return {prefix: tree}
    out: dict[Path_, Any] = {}
    for key, value in tree.items():
        out.update(
            flatten(value, (*prefix, key)) if isinstance(value, dict) else {(*prefix, key): value}
        )
    return out


def unflatten(leaves: dict[Path_, Any]) -> dict[str, Any]:
    tree: dict[str, Any] = {}
    for path, value in leaves.items():
        node = tree
        for key in path[:-1]:
            node = node.setdefault(key, {})
        node[path[-1]] = value
    return tree


def _number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def merge_budgets(  # noqa: PLR0912 - one pass per leaf, then one per reason
    base: dict[str, Any], ours: dict[str, Any], theirs: dict[str, Any]
) -> dict[str, Any]:
    """Three-way merge of the budget document (see the module docstring)."""
    b, o, t = flatten(base), flatten(ours), flatten(theirs)
    order = [*o, *(p for p in t if p not in o)]
    merged: dict[Path_, Any] = {}
    winner: dict[Path_, dict[Path_, Any] | None] = {}  # the side that won a leaf; None = a tie
    for path in (p for p in order if p[0] != "reasons"):
        in_o, in_t = path in o, path in t
        if in_o and in_t:
            a, c = o[path], t[path]
            if a == c:
                merged[path], winner[path] = a, None
            elif _number(a) and _number(c):
                merged[path], winner[path] = (a, o) if a >= c else (c, t)
            elif a == b.get(path, _GONE):
                merged[path], winner[path] = c, t
            else:
                merged[path], winner[path] = a, o
        else:
            side = o if in_o else t
            if path in b:
                continue  # the other side removed it: removed, whatever this side changed
            merged[path], winner[path] = side[path], side
    by_key = {".".join(p): p for p in merged}
    reasons: dict[str, Any] = {}
    for path in (p for p in order if p[0] == "reasons"):
        key = ".".join(path[1:])
        if key in reasons or key not in by_key:
            continue  # seen already, or the budget it explains is gone
        side = winner[by_key[key]]
        if side is None:  # equal numbers: the reason that changed, ours first
            changed = [s for s in (o, t) if path in s and s[path] != b.get(path)] or [o, t]
            side = next(s for s in changed if path in s)
        elif path not in side:
            side = o if side is t else t
        if path in side:
            reasons[key] = side[path]
    out = unflatten(merged)
    if reasons or "reasons" in ours or "reasons" in theirs:
        out["reasons"] = reasons
    return _ordered(out, ours)


def _ordered(tree: dict[str, Any], like: dict[str, Any]) -> dict[str, Any]:
    """Top-level keys in ``like``'s order (the shape the writer produces), the rest after."""
    first = {k: tree[k] for k in like if k in tree}
    return {**first, **{k: v for k, v in tree.items() if k not in first}}


def merge_views(
    base: dict[str, Any], ours: dict[str, Any], theirs: dict[str, Any]
) -> dict[str, Any]:
    """Union of ``views`` by key; the changed side wins (ours if both); newest ``generated``."""
    bv, ov, tv = (d.get("views", {}) for d in (base, ours, theirs))
    views: dict[str, Any] = {}
    for key in [*ov, *(k for k in tv if k not in ov)]:
        in_o, in_t = key in ov, key in tv
        if in_o and in_t:
            views[key] = tv[key] if ov[key] == bv.get(key, _GONE) else ov[key]
        elif in_o and not (key in bv and bv[key] == ov[key]):
            views[key] = ov[key]
        elif in_t and not (key in bv and bv[key] == tv[key]):
            views[key] = tv[key]
    generated = max(str(ours.get("generated", "")), str(theirs.get("generated", "")))
    out = {k: v for k, v in ours.items() if k != "views"}
    out["generated"] = generated
    out["views"] = views
    return out


def dumps(doc: dict[str, Any], like: str) -> str:
    """Serialise like ``like`` (the file as it was): compact or indent N, inline scalar lists."""
    stripped = like.strip()
    if "\n" not in stripped:
        return json.dumps(doc) + "\n"
    indent = len(stripped.splitlines()[1]) - len(stripped.splitlines()[1].lstrip())
    text = json.dumps(doc, indent=indent, ensure_ascii=False)
    if "[\n" in like and not _INLINE.search(like):
        return text + "\n"
    if not re.search(r'\[(?:"|-?\d)[^\]\n]*\]', like):
        return text + "\n"  # the file keeps its lists multi-line
    return _INLINE.sub(lambda m: "[" + re.sub(r",\s+", ", ", m.group(1)) + "]", text) + "\n"


def run(kind: str, base_p: Path, ours_p: Path, theirs_p: Path) -> int:
    ours_text = ours_p.read_text()
    try:
        base = json.loads(base_p.read_text())
        ours, theirs = json.loads(ours_text), json.loads(theirs_p.read_text())
        merge = merge_budgets if kind == "budgets" else merge_views
        result = dumps(merge(base, ours, theirs), ours_text)
    except (OSError, ValueError, KeyError, AttributeError, TypeError):
        # fall back: a normal conflict file, markers in %A
        subprocess.run(["git", "merge-file", str(ours_p), str(base_p), str(theirs_p)], check=False)
        return 1
    ours_p.write_text(result)
    return 0


def main(argv: list[str]) -> int:
    if len(argv) < 5 or argv[1] not in {"budgets", "views"}:
        print(__doc__, file=sys.stderr)
        return 2
    return run(argv[1], Path(argv[2]), Path(argv[3]), Path(argv[4]))


if __name__ == "__main__":
    sys.exit(main(sys.argv))
