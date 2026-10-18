"""The preview's budget (ADR 0029): p95 <= 1 s cold (field frame read) and <= 200 ms warm
(an edit re-evaluated in memory) on a store sized up synthetically to 5,000 instruments x 20
fields. CPU time, not wall time: tests run in parallel, so waiting for a CPU is noise; and
measured with coverage paused, since line tracing slows pure Python 2-3x.

The strict budgets are the ``perf`` test, run on an idle machine (``make perf``); they fail
whenever the machine is loaded, so the default run (``make test``, CI) excludes ``perf``. The
default run keeps two machine-independent guards instead, both by median: each preview at
most 5x its usual cost in units of a reference workload (a catastrophic regression), and warm
at most half of cold (the cache and the memo work). CPU time alone is not machine-independent:
a loaded machine or a shared CI runner inflates it 3-14x on this path (warm p95 306 ms, 490 ms,
1.04 s, 1.13 s on CI vs ~80 ms on an idle Mac), so an absolute ceiling there was flaky. The
reference is pure Python shaped like the warm path, timed just before every sample, so both
see the same machine; the median drops the odd descheduled sample that sets a p95 of 20."""

import sys
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import date
from typing import Any

import numpy as np
import pytest

from algotrade.config.user import UserContext
from algotrade.data import StoreReader
from algotrade.services.preview.screens import preview_screen
from algotrade.services.read.context import ResultCache, open_context
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.configs.files import MemoryConfigStore
from algotrade.storage.tables.writers import StoreWriter
from tests.helpers.stored_frames import reference_rows, stamped, universe_rows

pytestmark = pytest.mark.slow

COLD, WARM = 1.0, 0.2  # p95 budgets in CPU seconds (the perf test)
# The usual median cost in reference units, the top of what was measured on 2026-10-18 at load
# 34 to 82 on a 10-core Mac, alone and as 6 parallel copies (cold 20-35, warm 7.5-9.0, while
# the warm CPU median moved 258-339 ms and its p95 500-660 ms), and the default run's ceiling
# multiple of it (see above).
COLD_REFS, WARM_REFS = 35.0, 9.0
LOOSE = 5.0

DAY = date(2026, 10, 2)
N = 5_000
LIQ, PS = "rollup.option_liquidity@v1", "rollup.price_stats@v2"
LIQ_COLUMNS = {
    "chain_oi": "int", "chain_volume": "int", "underlying_price": "float", "iv30": "float",
    "stock_volume": "float", "put_delta": "float", "put_spread_pct": "float", "put_tier": "str",
    "call_spread_pct": "float", "target_dte": "int",
}  # fmt: skip
PS_COLUMNS = ("close", "sma_20", "sma_50", "sma_200", "ret_20d", "ret_60d", "high_52w",
              "low_52w", "hv20", "hv30")  # fmt: skip
SPEC: dict[str, Any] = {
    "id": "perf",
    "kind": "screener",
    "impl": "rules",
    "selection": "active",
    "criteria": {
        "price": {"field": f"{LIQ}.underlying_price", "op": "gt", "value": 20},
        "oi": {"field": f"{LIQ}.chain_oi", "op": "gte", "value": 2000, "mode": "soft",
               "tolerance": {"relative": 0.3}},
        "spread": {"field": f"{LIQ}.put_spread_pct", "op": "lte", "value": 0.1, "mode": "soft",
                   "tolerance": 0.05},
        "trend": {"field": f"{PS}.close", "op": "gt", "value": 50},
        "vol": {"field": f"{PS}.hv30", "op": "between", "value": [0.1, 0.8]},
        "momentum": {"field": f"{PS}.ret_60d", "op": "gt", "value": 0, "mode": "score"},
        "iv": {"field": f"{LIQ}.iv30", "op": "gte", "value": 0.2, "mode": "score"},
        "dte": {"field": f"{LIQ}.target_dte", "op": "between", "value": [20, 60]},
    },
    "tiers": {"a": {"all": [{"field": f"{LIQ}.put_tier", "op": "eq", "value": "A"}]}},
    "flags": {"liquid": {"all": [{"field": f"{LIQ}.chain_volume", "op": "gt", "value": 5000}]}},
    "classify": f"{LIQ}.put_tier",
    "columns": {c: f"{PS}.{c}" for c in PS_COLUMNS if c not in ("close", "hv30", "ret_60d")}
    | {"volume": f"{LIQ}.stock_volume", "call_spread": f"{LIQ}.call_spread_pct",
       "delta": f"{LIQ}.put_delta", "chain_volume": f"{LIQ}.chain_volume",
       "put_tier": f"{LIQ}.put_tier"},
    "rank": {"tie_break": f"{LIQ}.chain_oi"},
}  # fmt: skip
ACTIVE = {
    "name": "active",
    "where": {"all": [{"field": "instrument.status", "op": "eq", "value": "ACTIVE"}]},
}


def _store() -> tuple[StoreReader, MemoryConfigStore]:
    rng = np.random.default_rng(7)
    symbols = [f"S{i:05d}" for i in range(N)]
    ids = [f"EQ:{s}" for s in symbols]
    writer = StoreWriter(backend := MemoryBackend())
    universe = universe_rows(symbols, last_verified=DAY.isoformat())
    writer.write_table("universe", DAY, "u1", stamped(universe, DAY, "u1"))
    reference = reference_rows(universe)
    writer.write_table("instruments/reference", DAY, "u1", stamped(reference, DAY, "u1"))
    liq: dict[str, Any] = {"instrument_id": ids}
    for name, kind in LIQ_COLUMNS.items():
        if kind == "str":
            liq[name] = rng.choice(["A", "B", "C"], N).tolist()
        elif kind == "int":
            liq[name] = rng.integers(0, 10_000, N).tolist()
        else:
            liq[name] = rng.uniform(0, 100, N).round(4).tolist()
    liq["put_spread_pct"] = rng.uniform(0, 0.3, N).tolist()
    liq["target_dte"] = rng.integers(5, 90, N).tolist()
    rows = [dict(zip(liq, v, strict=True)) for v in zip(*liq.values(), strict=True)]
    table = "rollups/instrument/option_liquidity@v1"
    writer.write_table(table, DAY, "f1", stamped(rows, DAY, "f1"))
    ps = {c: rng.uniform(0.05, 150, N).astype("float32") for c in PS_COLUMNS}
    frame = stamped([{"instrument_id": i} for i in ids], DAY, "f2")
    for c, values in ps.items():
        frame[c] = values
    writer.write_table("rollups/instrument/price_stats@v2", DAY, "f2", frame)
    configs = MemoryConfigStore({("site", "selections", "active"): ACTIVE})
    return StoreReader(backend), configs


@pytest.fixture(scope="module")
def sized() -> tuple[StoreReader, MemoryConfigStore]:
    return _store()


@contextmanager
def untraced() -> Iterator[None]:
    """Line tracing (``pytest --cov``) off in this thread, so the timing is the code's."""
    tracer = sys.gettrace()
    sys.settrace(None)
    try:
        yield
    finally:
        sys.settrace(tracer)


_REFERENCE_ROWS = [
    {f"f{j}": float(v) for j, v in enumerate(row)}
    for row in np.random.default_rng(1).uniform(0, 100, (20_000, 20))
]


def reference() -> object:
    """A fixed pure-Python workload shaped like the warm path (filter dict rows, rank, copy
    the top): the machine's speed right now, the unit the default run's ceiling is in."""
    rows = _REFERENCE_ROWS
    kept = [(r["f3"], i) for i, r in enumerate(rows) if r["f0"] > 20 and 5 <= r["f2"] <= 90]
    kept.sort(reverse=True)
    return [dict(rows[i]) for _, i in kept[:100]], sum(r["f4"] * r["f5"] for r in rows)


def cpu(run: Callable[[], object]) -> float:
    started = time.process_time()
    run()
    return time.process_time() - started


def timings(run: Callable[[], object], times: int) -> tuple[list[float], list[float]]:
    """``times`` CPU timings of ``run``, each with the reference timed just before it."""
    taken, refs = [], []
    with untraced():
        for _ in range(times):
            refs.append(cpu(reference))
            taken.append(cpu(run))
    return taken, refs


Samples = tuple[list[float], list[float]]  # (seconds, reference seconds), sample by sample


def measure(sized: tuple[StoreReader, MemoryConfigStore]) -> tuple[Samples, Samples]:
    reader, configs = sized
    user = UserContext("alice")
    fields = {SPEC["criteria"][c]["field"] for c in SPEC["criteria"]}
    assert len(fields | set(SPEC["columns"].values())) >= 20

    ctx = open_context(reader, configs, user, DAY)

    def cold() -> object:
        got = preview_screen(ctx, ResultCache(4), SPEC, limit=100)  # a fresh cache: read
        assert not got.cached and got.total == N
        return got

    shared = ResultCache(4)
    preview_screen(ctx, shared, SPEC)
    edits = iter(range(10_000))

    def warm() -> object:  # a threshold edit: same fields, re-evaluated in memory
        spec = {**SPEC, "criteria": {**SPEC["criteria"], "price": {
            **SPEC["criteria"]["price"], "value": 10 + next(edits) % 50}}}  # fmt: skip
        got = preview_screen(ctx, shared, spec, limit=100)
        assert got.cached
        return got

    return timings(cold, 5), timings(warm, 20)


def test_cold_and_warm_previews_stay_within_a_loose_ceiling(
    sized: tuple[StoreReader, MemoryConfigStore],
) -> None:
    (colds, cold_refs), (warms, warm_refs) = measure(sized)
    cold = float(np.median(np.divide(colds, cold_refs)))
    warm = float(np.median(np.divide(warms, warm_refs)))
    seen = "cpu ms cold {} warm {}, reference ms {} {}".format(
        *([round(x * 1000) for x in xs] for xs in (colds, warms, cold_refs, warm_refs))
    )
    assert cold <= COLD_REFS * LOOSE, f"cold {cold:.1f} refs (ceiling {COLD_REFS * LOOSE}) {seen}"
    assert warm <= WARM_REFS * LOOSE, f"warm {warm:.1f} refs (ceiling {WARM_REFS * LOOSE}) {seen}"
    assert np.median(warms) <= 0.5 * np.median(colds), seen


@pytest.mark.perf
def test_cold_and_warm_previews_meet_the_budget(
    sized: tuple[StoreReader, MemoryConfigStore],
) -> None:
    (colds, _), (warms, _) = measure(sized)
    cold_p95, warm_p95 = float(np.percentile(colds, 95)), float(np.percentile(warms, 95))
    assert cold_p95 <= COLD, f"cold p95 {cold_p95:.3f}s (budget {COLD}s)"
    assert warm_p95 <= WARM, f"warm p95 {warm_p95:.3f}s (budget {WARM}s)"
    assert np.median(warms) <= 0.5 * np.median(colds), (colds, warms)
