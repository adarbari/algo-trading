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
