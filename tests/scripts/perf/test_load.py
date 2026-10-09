"""`scripts/perf/load.py`: percentiles, the operation documents parsed from gql.ts, the
per-page summary and the printed table (no server)."""

import asyncio
import importlib.util
import random
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
    wanted = {op.name for p in load.PAGES for op in load.page_ops(p)}
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


def test_every_page_sends_the_shell_once() -> None:
    for page in load.PAGES:
        names = [op.name for op in load.page_ops(page)]
        assert {"Viewer", "StatusStrip", "Regime"} <= set(names)
        assert len(names) == len(set(names))


def test_busy_delay_matches_the_web_client() -> None:
    assert load.busy_delay("2", 0, 0.5) == pytest.approx(2.0)
    assert load.busy_delay(None, 2, 0.0) == pytest.approx(1.0)  # 1 * 2 * 0.5
    assert load.busy_delay("junk", 0, 0.99) == pytest.approx(1.49)


def test_think_time_is_exponential_with_the_mean() -> None:
    rng = random.Random(1)
    draws = [load.think_time(10.0, rng) for _ in range(20000)]
    assert sum(draws) / len(draws) == pytest.approx(10.0, rel=0.05)
    assert load.think_time(0, rng) == 0.0


def test_response_cause_names_status_and_first_graphql_message() -> None:
    assert load.response_cause(200, {"data": {}}) is None
    assert load.response_cause(502, None) == "HTTP 502"
    assert load.response_cause(200, {"errors": [{"message": "boom"}]}) == "GraphQL: boom"


class _Resp:
    def __init__(self, status: int, body=None, headers=None) -> None:
        self.status_code, self._body, self.headers = status, body or {"data": {}}, headers or {}

    def json(self):
        return self._body


class _Client:
    def __init__(self, *outcomes) -> None:
        self.outcomes = list(outcomes)

    async def post(self, *_a, **_k):
        out = self.outcomes.pop(0)
        if isinstance(out, Exception):
            raise out
        return out


def _run_op(client, sleeps: list):
    async def sleep(s):
        sleeps.append(s)

    op = load.Op("X", lambda _s: {})
    return asyncio.run(load._op(client, {"X": "query X { x }"}, op, None, sleep=sleep))


def test_op_retries_503_then_succeeds() -> None:
    sleeps: list = []
    busy = _Resp(503, headers={"retry-after": "1"})
    res = _run_op(_Client(busy, busy, _Resp(200)), sleeps)
    assert not res.failed and res.seen_503 == 2 and len(sleeps) == 2


def test_op_gives_up_after_the_retries_and_names_the_cause() -> None:
    sleeps: list = []
    res = _run_op(_Client(*[_Resp(503)] * (load.BUSY_RETRIES + 1)), sleeps)
    assert res.failed and res.cause == "HTTP 503"
    assert res.seen_503 == load.BUSY_RETRIES + 1 and len(sleeps) == load.BUSY_RETRIES


def test_op_records_exception_class_and_graphql_error() -> None:
    res = _run_op(_Client(RuntimeError("closed")), [])
    assert res.failed and res.cause == "exception RuntimeError"
    res = _run_op(_Client(_Resp(200, {"errors": [{"message": "bad"}]})), [])
    assert res.failed and res.cause == "GraphQL: bad"


def test_summarise_counts_errors_by_cause() -> None:
    rows = load.summarise([load.PageLoad("a", 1.0, 2, 0, ["HTTP 500", "HTTP 500"])])
    assert rows["a"]["causes"] == {"HTTP 500": 2}


def _level(p95: float, rate: float, rss: float, health: float) -> dict:
    page = {"loads": 100, "p95": p95, "error_rate": rate}
    return {"pages": {"a": page}, "resources": {"peak_rss_mb": rss}, "health": {"p99": health}}


def test_verdict_passes_and_fails_on_each_criterion() -> None:
    assert load.verdict(_level(2.0, 0.0, 1500, 0.1))[0]
    bad_levels = (
        _level(3, 0, 1, 0),
        _level(1, 0.01, 1, 0),
        _level(1, 0, 3000, 0),
        _level(1, 0, 1, 0.3),
    )
    for bad in bad_levels:
        ok, lines = load.verdict(bad)
        assert not ok and any("FAIL" in line for line in lines)


def test_client_keepalive_expires_before_uvicorn_closes_idle_connections() -> None:
    assert load.KEEPALIVE_EXPIRY < 5.0
