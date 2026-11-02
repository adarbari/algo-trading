"""`scripts/ops/merge_budgets.py`, the git merge driver of the shared perf and latency JSON
files (owner decision 2026-11-02: five UI PRs re-conflicted on them at every merge to main)."""

import importlib.util
import json
from pathlib import Path
from typing import Any

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "ops" / "merge_budgets.py"
spec = importlib.util.spec_from_file_location("merge_budgets", SCRIPT)
assert spec and spec.loader
mb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mb)

BASE: dict[str, Any] = {
    "bundle": {"entry_gzip_bytes": 100, "routes": {"a.ts": 10, "old.ts": 5}},
    "e2e": {"/ideas": {"requests": 70}, "/gone": {"requests": 9}},
    "reasons": {
        "bundle.routes.a.ts": "base a",
        "bundle.routes.old.ts": "base old",
        "e2e./gone.requests": "base gone",
    },
}


def doc(**routes: int) -> dict[str, Any]:
    d = json.loads(json.dumps(BASE))
    d["bundle"]["routes"].update(routes)
    return d


def test_union_max_and_the_reason_of_the_winning_number() -> None:
    ours = doc(a_ts_placeholder=0)
    del ours["bundle"]["routes"]["a_ts_placeholder"]
    ours["bundle"]["routes"].update({"a.ts": 12, "mine.ts": 3})
    ours["reasons"].update({"bundle.routes.a.ts": "ours a", "bundle.routes.mine.ts": "mine"})
    theirs = doc()
    theirs["bundle"]["routes"].update({"a.ts": 15, "theirs.ts": 4})
    theirs["reasons"].update({"bundle.routes.a.ts": "theirs a", "bundle.routes.theirs.ts": "t"})
    out = mb.merge_budgets(BASE, ours, theirs)
    routes = out["bundle"]["routes"]
    assert routes["a.ts"] == 15 and routes["mine.ts"] == 3 and routes["theirs.ts"] == 4
    assert out["reasons"]["bundle.routes.a.ts"] == "theirs a"  # the larger number's reason
    assert out["reasons"]["bundle.routes.mine.ts"] == "mine"
    assert out["reasons"]["bundle.routes.theirs.ts"] == "t"


def test_a_route_removed_on_one_side_goes_with_its_e2e_entry_and_reasons() -> None:
    theirs = doc()
    del theirs["e2e"]["/gone"], theirs["reasons"]["e2e./gone.requests"]
    ours = doc()
    ours["bundle"]["routes"]["a.ts"] = 11
    out = mb.merge_budgets(BASE, ours, theirs)
    assert "/gone" not in out["e2e"] and "e2e./gone.requests" not in out["reasons"]
    assert out["bundle"]["routes"]["a.ts"] == 11


def test_a_removal_wins_over_a_raise_on_the_other_side() -> None:
    # 2026-11-02 #1035: the branch removed two pages and their e2e routes while main raised
    # their budgets; keeping the raises left page budgets without pages and half e2e entries
    base = json.loads(json.dumps(BASE))
    base["e2e"]["/gone"].update({"dom_nodes": 200, "first_load_js_gzip_bytes": 1000})
    removed = json.loads(json.dumps(base))
    del removed["e2e"]["/gone"], removed["bundle"]["routes"]["old.ts"]
    for key in ("e2e./gone.requests", "bundle.routes.old.ts"):
        del removed["reasons"][key]
    raised = json.loads(json.dumps(base))
    raised["e2e"]["/gone"]["requests"] = 12
    raised["bundle"]["routes"]["old.ts"] = 6
    raised["reasons"]["e2e./gone.requests"] = "main raised it"
    for ours, theirs in ((removed, raised), (raised, removed)):
        out = mb.merge_budgets(base, ours, theirs)
        assert "/gone" not in out["e2e"] and "old.ts" not in out["bundle"]["routes"]
        assert "e2e./gone.requests" not in out["reasons"]
        assert "bundle.routes.old.ts" not in out["reasons"]


def test_an_orphan_reason_is_dropped() -> None:
    ours = doc()
    ours["reasons"]["bundle.routes.nothing.ts"] = "no budget"
    assert "bundle.routes.nothing.ts" not in mb.merge_budgets(BASE, ours, doc())["reasons"]


def git_merge(tmp_path: Path, kind: str, base: str, ours: str, theirs: str) -> tuple[int, str]:
    for name, text in (("base", base), ("ours", ours), ("theirs", theirs)):
        (tmp_path / name).write_text(text)
    rc = mb.run(kind, tmp_path / "base", tmp_path / "ours", tmp_path / "theirs")
    return rc, (tmp_path / "ours").read_text()


def test_the_driver_writes_the_file_in_its_own_format(tmp_path: Path) -> None:
    text = json.dumps({"bundle": {"routes": {"a": 1}, "lazy": ["x.ts"]}}, indent=2) + "\n"
    text = text.replace('[\n      "x.ts"\n    ]', '["x.ts"]')
    theirs = text.replace('"a": 1', '"a": 2')
    rc, out = git_merge(tmp_path, "budgets", text, text, theirs)
    assert rc == 0 and out == theirs


def test_unparsable_json_falls_back_to_a_normal_conflict(tmp_path: Path) -> None:
    rc, out = git_merge(tmp_path, "budgets", "{}\n", "{ not json\n", '{"a": 1}\n')
    assert rc == 1
    assert "<<<<<<<" in out and ">>>>>>>" in out


def view(op: str, captured: bool = False) -> dict[str, Any]:
    return {"route": "/r", "ops": [op], **({"captured": {"status": "ok"}} if captured else {})}


def test_captured_views_are_unioned_and_our_changed_entry_wins() -> None:
    base = {"generated": "d1", "views": {"keep": view("A", True), "mine": view("B", True)}}
    ours = {
        "generated": "d1",
        "views": {"keep": view("A", True), "mine": view("B2"), "new_ours": view("N", True)},
    }
    theirs = {
        "generated": "d2",
        "views": {"keep": view("A2", True), "mine": view("B", True), "new_theirs": view("T")},
    }
    out = mb.merge_views(base, ours, theirs)
    assert list(out["views"]) == ["keep", "mine", "new_ours", "new_theirs"]
    assert out["views"]["keep"]["ops"] == ["A2"]  # only theirs changed it
    assert out["views"]["mine"]["ops"] == ["B2"]  # ours changed it: ours wins
    assert out["views"]["keep"]["captured"] and out["views"]["new_ours"]["captured"]
    assert out["generated"] == "d2"
    # a view theirs dropped (ours unchanged) stays dropped
    gone = {"generated": "d2", "views": {"mine": view("B", True)}}
    assert "keep" not in mb.merge_views(base, base, gone)["views"]
