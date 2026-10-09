"""`scripts/perf/load.py`: percentiles, the operation documents parsed from gql.ts, the
per-page summary and the printed table (no server)."""

import importlib.util
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "perf" / "load.py"
_spec = importlib.util.spec_from_file_location("perf_load", SCRIPT)
assert _spec and _spec.loader
load = importlib.util.module_from_spec(_spec)
sys.modules["perf_load"] = load
_spec.loader.exec_module(load)


def test_percentile_interpolates_and_handles_empty() -> None:
    assert load.percentile([], 50) == 0.0
    assert load.percentile([5.0], 99) == 5.0
    assert load.percentile([1, 2, 3, 4], 50) == pytest.approx(2.5)
    assert load.percentile([4, 1, 3, 2], 100) == 4


def test_parse_documents_reads_names_from_the_documents_map() -> None:
    ts = (
        "type Documents = {\n"
        '    "\\n  query Viewer {\\n    viewer { id }\\n  }\\n": typeof types.V,\n'
        '    "\\n  query NightlyRuns($limit: Int!) {\\n    x\\n  }\\n": typeof types.N,\n'
        "};\n"
    )
    docs = load.parse_documents(ts)
    assert set(docs) == {"Viewer", "NightlyRuns"}
    assert "viewer { id }" in docs["Viewer"]


def test_every_page_operation_is_in_the_generated_documents() -> None:
    docs = load.parse_documents(load.GQL_TS.read_text())
    wanted = {op.name for ops in load.PAGES.values() for op in ops}
    assert wanted <= set(docs)


def test_summarise_per_page() -> None:
    loads = [
        load.PageLoad("a", 1.0),
        load.PageLoad("a", 3.0, errors=1, unavailable=1),
        load.PageLoad("b", 2.0),
    ]
    rows = load.summarise(loads)
    assert rows["a"]["loads"] == 2 and rows["a"]["p50"] == pytest.approx(2.0)
    assert rows["a"]["error_rate"] == 0.5 and rows["a"]["rate_503"] == 0.5
    assert rows["b"]["error_rate"] == 0.0


def test_render_table_has_a_row_per_page() -> None:
    report = {
        "scenario": "warm",
        "seconds": 5,
        "url": "u",
        "levels": [
            {
                "users": 100,
                "loads": 3,
                "pages": load.summarise([load.PageLoad("ideas", 1.5)]),
                "resources": {"peak_rss_mb": 512.0, "mean_cpu_pct": 80.0},
            }
        ],
    }
    text = load.render_table(report)
    assert "100 users" in text and "ideas" in text and "512 MB" in text
