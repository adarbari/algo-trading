"""A small store for the screen read objects, read as user ``me`` for the latest session D1.

Configs: site presets ``alpha`` (named "Alpha") and ``beta``; ``me`` has its own ``beta`` (so
the site's ``beta`` is not one of ``me``'s screeners) and ``gamma`` (never run on D1).
Results on D1: ``alpha`` (site) ran twice (``r0`` then ``r1``: ``r1`` is the latest),
``beta`` ran for ``me`` and for ``site``; on D0 (an older session) ``gamma`` ran, which a D1
read must never show, and ``alpha`` ran (``r-1``: AAA REJECT, BBB and CCC QUALIFIED; the run
D1's ``alpha`` is compared with). ``rule_screen_values`` hold ``alpha``'s criteria and a
display column."""

from collections.abc import Mapping
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pandas as pd
import pytest

from algotrade.config.user import UserContext
from algotrade.data import StoreReader
from algotrade.services.read.context import ReadContext, open_context
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.configs.files import MemoryConfigStore
from algotrade.storage.runs import RunRecord
from algotrade.storage.tables.writers import StoreWriter
from tests.helpers.stored_frames import stamped, write_reference

D0, D1 = date(2026, 9, 30), date(2026, 10, 1)
T = datetime(2026, 10, 2, 3, tzinfo=UTC)
SYMBOLS = ("AAA", "BBB", "CCC", "DDD")


def _screen(config_id: str, name: str | None = None, version: int = 1) -> dict[str, object]:
    doc: dict[str, object] = {
        "id": config_id, "kind": "screener", "impl": "rules", "version": version,
        "selection": "all_active",
        "criteria": {"price": {"field": "rollup.price_stats@v2.close", "op": "gt", "value": 5,
                               "mode": "hard"}},
    }  # fmt: skip
    if name is not None:
        doc["name"] = name
    return doc


Docs = Mapping[tuple[str, str, str], Mapping[str, Any]]
CONFIGS: Docs = {
    ("site", "selections", "all_active"): {
        "name": "all_active",
        "where": {"all": [{"field": "instrument.status", "op": "eq", "value": "ACTIVE"}]},
    },
    ("site", "screeners", "alpha@1"): _screen("alpha", " Alpha "),
    ("site", "screeners", "beta@1"): _screen("beta"),
    ("me", "screeners", "beta@2"): _screen("beta", "My beta", version=2),
    ("me", "screeners", "gamma@1"): _screen("gamma"),
}


def write_run(
    writer: StoreWriter,
    day: date,
    run_id: str,
    owner: str,
    config_id: str,
    rows: list[tuple[str, str, float | None, float | None]],
    knowledge: datetime = T,
) -> None:
    """``rows``: (symbol, decision, score, tie-break), ranked in the order given."""
    frame = [
        {"instrument_id": f"EQ:{s}", "user_id": owner, "config_id": config_id,
         "config_version": 1, "config_hash": "h", "decision": d, "score": sc, "rank": n,
         "tie_break": tb, "flags": "large_move" if s == "BBB" else "", "reasons": "",
         "failed": "", "near_missed": "", "missing": ""}
        for n, (s, d, sc, tb) in enumerate(rows, start=1)
    ]  # fmt: skip
    writer.write_result("rule_screen", day, run_id, stamped(frame, day, run_id, knowledge))


def _values(writer: StoreWriter) -> None:
    rows = [
        {"instrument_id": "EQ:BBB", "user_id": "site", "config_id": "alpha",
         "criterion_id": "iv_rank", "field": "rollup.x@v1.iv_rank", "mode": "soft",
         "value_num": 40.0, "value_str": None, "outcome": "NEAR", "distance": 10.0},
        {"instrument_id": "EQ:AAA", "user_id": "site", "config_id": "alpha",
         "criterion_id": "spread", "field": "feature.spread", "mode": "column",
         "value_num": 0.05, "value_str": None, "outcome": "INFO", "distance": None},
        {"instrument_id": "EQ:AAA", "user_id": "site", "config_id": "alpha",
         "criterion_id": "iv30", "field": "feature.vrp_iv30", "mode": "hard",
         "value_num": None, "value_str": "high", "outcome": "PASS", "distance": None},
    ]  # fmt: skip
    writer.write_result("rule_screen_values", D1, "r1", stamped(rows, D1, "r1", T))


@pytest.fixture
def backend() -> MemoryBackend:
    store = MemoryBackend()
    w = StoreWriter(store)
    write_reference(w, D0, {s: f"EQ:{s}" for s in SYMBOLS})
    for day in (D0, D1):
        bar = {"instrument_id": "EQ:AAA", "ts": pd.Timestamp(day, tz="UTC"), "open": 1.0,
               "high": 1.0, "low": 1.0, "close": 1.0, "volume": 1.0}  # fmt: skip
        w.write_table("bars/1d", day, f"bars-{day}", stamped([bar], day, f"bars-{day}"))
    write_run(w, D1, "r0", "site", "alpha", [("DDD", "QUALIFIED", 99.0, None)])
    write_run(
        w,
        D1,
        "r1",
        "site",
        "alpha",
        [
            ("AAA", "QUALIFIED", 50.0, None),
            ("BBB", "WATCH", 70.0, 2.0),
            ("CCC", "REJECT", 0.0, None),
        ],
        knowledge=T + timedelta(hours=1),
    )
    write_run(w, D1, "rb", "me", "beta",
              [("BBB", "QUALIFIED", 90.0, None), ("DDD", "QUALIFIED", 10.0, None),
               ("AAA", "SKIPPED", None, None)])  # fmt: skip
    write_run(w, D1, "rs", "site", "beta", [("CCC", "QUALIFIED", 99.0, None)])
    write_run(w, D0, "rg", "me", "gamma", [("CCC", "QUALIFIED", 80.0, None)])
    write_run(w, D0, "r-1", "site", "alpha",
              [("BBB", "QUALIFIED", 90.0, None), ("CCC", "QUALIFIED", 80.0, None),
               ("AAA", "REJECT", 0.0, None)])  # fmt: skip
    _values(w)
    w.save_run(RunRecord("r1", "screen-alpha-site", D1, T).finish(T))
    return store


@pytest.fixture
def reader(backend: MemoryBackend) -> StoreReader:
    return StoreReader(backend)


def context(reader: StoreReader, docs: Docs | None = None, user: str = "me") -> ReadContext:
    return open_context(reader, MemoryConfigStore({**CONFIGS, **(docs or {})}), UserContext(user))


@pytest.fixture
def ctx(reader: StoreReader) -> ReadContext:
    """``me``'s read context for the latest session, D1."""
    return context(reader)


def write_gated(backend: MemoryBackend) -> None:
    """A later ``alpha`` run (``r2``, supersedes ``r1``) of the gate in STORM (ADR 0049): AAA
    QUALIFIED, BBB and DDD PAUSED with the reason first, CCC REJECT; each row stamps the label
    and the size 0.5."""
    why = "regime=STRESS: alpha"
    gated = [("AAA", "QUALIFIED", 50.0, ""), ("BBB", "PAUSED", 70.0, why),
             ("CCC", "REJECT", 0.0, ""), ("DDD", "PAUSED", 40.0, why)]  # fmt: skip
    frame = [
        {"instrument_id": f"EQ:{s}", "user_id": "site", "config_id": "alpha",
         "config_version": 1, "config_hash": "h", "decision": d, "score": sc, "rank": n,
         "tie_break": None, "flags": "", "reasons": why, "failed": "", "near_missed": "",
         "missing": "", "regime": "STRESS", "size_multiplier": 0.5}
        for n, (s, d, sc, why) in enumerate(gated, start=1)
    ]  # fmt: skip
    knowledge = T + timedelta(hours=2)
    StoreWriter(backend).write_result("rule_screen", D1, "r2", stamped(frame, D1, "r2", knowledge))
