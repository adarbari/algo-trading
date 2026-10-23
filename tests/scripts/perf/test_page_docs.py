"""`scripts/perf/page_docs.py`: the recorded benchmark documents equal the web's generated ones."""

import importlib.util
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
SCRIPT = REPO / "scripts" / "perf" / "page_docs.py"
_spec = importlib.util.spec_from_file_location("perf_page_docs", SCRIPT)
assert _spec and _spec.loader
pd = importlib.util.module_from_spec(_spec)
sys.modules["perf_page_docs"] = pd
_spec.loader.exec_module(pd)

DOCS = {"X": "query X($first: Int!) {\n  x(first: $first)\n}\n"}


def call(op: str, query: str, variables: dict) -> dict:
    return {"kind": "graphql", "op": op, "variables": variables, "query": query}


def test_recorded_documents_equal_the_webs_generated_documents() -> None:
    """Fitness: a recorded operation that differs from `gql.ts` (or is no web operation) fails.

    Fix: `make api-latency-docs ARGS=--write` (never a hand edit of the recording)."""
    pages = json.loads(pd.PAGES_FILE.read_text())["pages"]
    problems = pd.drift(pages, pd.web_documents(), pd.wpo.all_query_ops(pd.WEB_SRC))
    assert not problems, "\n".join(problems)


def test_drift_ignores_whitespace_and_flags_a_changed_document() -> None:
    same = call("X", "query X($first: Int!) { x(first: $first) }", {"first": 1})
    old = call("X", "query X($limit: Int!) { x(limit: $limit) }", {"limit": 1})
    assert pd.drift({"/a": [same]}, DOCS) == []
    assert "differs" in pd.drift({"/a": [old]}, DOCS)[0]


def test_drift_flags_a_renamed_variable_and_an_unknown_name() -> None:
    renamed = call("X", DOCS["X"], {"limit": 1})
    unknown = call("Z", "query Z { z }", {})
    assert "variables" in pd.drift({"/a": [renamed]}, DOCS)[0]
    assert "not a web operation" in pd.drift({"/a": [unknown]}, DOCS)[0]
    assert pd.drift({"/a": [unknown]}, DOCS, {"Z"}) == []


def test_sync_rewrites_documents_and_keeps_variables() -> None:
    pages = {"/a": [call("X", "query X { old }", {"first": 5}), call("Z", "query Z { z }", {})]}
    pd.sync(pages, DOCS)
    assert pages["/a"][0]["query"] == DOCS["X"]
    assert pages["/a"][0]["variables"] == {"first": 5}
    assert pages["/a"][1]["query"] == "query Z { z }"


def test_an_optional_variable_may_be_left_out_but_a_required_one_may_not() -> None:
    docs = {"X": "query X($first: Int!, $after: String) { x(first: $first, after: $after) }"}
    assert pd.drift({"/a": [call("X", docs["X"], {"first": 1})]}, docs) == []
    assert "variables" in pd.drift({"/a": [call("X", docs["X"], {"after": "a"})]}, docs)[0]


# Web query operations that neither benchmarks/api_latency_pages.json nor the static ops of
# benchmarks/api_latency_views.json list yet (the web's reads of an edge, the feature requests,
# an instrument's event list and history, a run's items). The gate measures some of them through
# crawled documents (`make api-latency-views-capture`), but a crawl is not a commitment: record
# each in the pages file (`make api-latency-capture`) and delete it here. Shrink-only: a NEW web
# operation must be measured, never added to this set.
UNMEASURED_BASELINE = {
    "AcceptedFormulas",
    "EdgeDetail",
    "EdgeDocument",
    "EdgeResultBasis",
    "InstrumentEventList",
    "InstrumentHistory",
    "MyFeatureRequests",
    "PublishedEdge",
    "RunItems",
}


def test_every_web_query_operation_is_measured_so_no_page_ships_unmeasured() -> None:
    """Fitness: each query operation the web declares is in the pages file or in a view's ops.

    Fix: record the page (`make api-latency-capture`) or enumerate its view
    (`make api-latency-views`); never add a name to UNMEASURED_BASELINE (it only shrinks)."""
    pages = json.loads(pd.PAGES_FILE.read_text())["pages"]
    views = json.loads((REPO / "benchmarks" / "api_latency_views.json").read_text())["views"]
    measured = {c["op"] for calls in pages.values() for c in calls if c["kind"] == "graphql"}
    measured |= {op for v in views.values() for op in v.get("ops", [])}
    unmeasured = pd.wpo.all_query_ops(pd.WEB_SRC) - measured
    assert not unmeasured - UNMEASURED_BASELINE, (
        f"web operations in no benchmark page or view: {sorted(unmeasured - UNMEASURED_BASELINE)}"
    )
    assert not UNMEASURED_BASELINE - unmeasured, (
        f"now measured, delete from UNMEASURED_BASELINE: {sorted(UNMEASURED_BASELINE - unmeasured)}"
    )
