"""The preview evaluates an unsaved draft with the nightly evaluator: equal rows to the stored
``results/rule_screen`` for the same session and spec, the funnel per gating criterion, the
warm path (edits re-evaluate in memory; a publish invalidates), fail-closed validation and no
writes."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any

import pandas as pd
import pytest

from algotrade.config.user import UserContext
from algotrade.core.model.errors import ConfigurationError
from algotrade.core.time.calendar import last_closed_session
from algotrade.services.configs import resolve_config
from algotrade.services.explore.preview.screens import preview_screen, preview_session
from algotrade.services.explore.store import ReadStore, store_over
from algotrade.services.screening.run import run_screener
from algotrade.services.views import to_value
from algotrade.storage.tables.writers import StoreWriter
from algotrade_sources.framework.base import FixtureSource
from tests.helpers.api_store import END, NOW, api_store
from tests.helpers.stored_frames import T0, stamped
from tests.unit.services.screening.test_rule_screens import DAY, LIQ, SCREEN, configs, seeded

ALICE = "alice"
DRAFT: dict[str, Any] = {k: v for k, v in SCREEN.items() if k != "version"} | {"id": "draft1"}


def plain(frame: pd.DataFrame) -> list[dict[str, Any]]:
    return [{k: to_value(v) for k, v in r.items()} for r in frame.to_dict("records")]


def preview_store() -> ReadStore:
    reader, _ = seeded()
    return ReadStore(reader, configs(), UserContext(ALICE))


def preview(store: ReadStore, spec: dict[str, Any] = DRAFT, limit: int = 1000) -> Any:
    return preview_screen(store, spec, ALICE, limit, on=DAY, now=T0)


def criterion(spec: dict[str, Any], cid: str, **changes: Any) -> dict[str, Any]:
    criteria = {**spec["criteria"], cid: {**spec["criteria"][cid], **changes}}
    return {**spec, "criteria": criteria}


def test_preview_rows_equal_the_nightly_rows() -> None:
    reader, writer = seeded()
    nightly = resolve_config(configs(), "big_liquid", UserContext(ALICE))
    run_screener(reader, writer, nightly, DAY, now=T0)
    stored = reader.table("results/rule_screen", DAY)
    assert stored is not None
    store = ReadStore(reader, configs(), UserContext(ALICE))
    got = preview(store, {**SCREEN, "id": "big_liquid"})
    assert {r.tier for r in got.rows} >= {"deep"} and any(r.flags for r in got.rows)
    assert got.config_hash == nightly.hash  # same spec, same user: the same config
    rows = pd.DataFrame(
        [
            {
                "instrument_id": r.instrument_id,
                "rank": r.rank,
                "decision": r.decision,
                "score": r.score,
                "tier": r.tier,
                "class": r.classification,
                "flags": ",".join(r.flags),
                "reasons": "; ".join(r.reasons),
            }
            for r in got.rows
        ]
    )
    want = stored.sort_values("rank")[list(rows.columns)].reset_index(drop=True)
    assert plain(rows) == plain(want)
    assert got.total == len(stored)


def test_summary_funnel_and_coverage() -> None:
    got = preview(preview_store())
    assert got.decisions == {"QUALIFIED": 1, "REJECT": 1, "SKIPPED": 1, "WATCH": 1}
    assert got.summary.passed == 1 and got.summary.skipped == 1
    assert got.summary.skipped_reasons == {
        f"no {LIQ}.chain_oi": 1,
        f"no {LIQ}.underlying_price": 1,
    }
    (miss,) = got.summary.narrow_misses
    assert (miss.instrument_id, miss.criterion_id, miss.distance) == ("EQ:BBB", "oi", 300)
    price, oi = got.funnel
    assert (price.entering, price.passed, price.failed, price.missing, price.remaining) == (
        4, 2, 1, 1, 2,
    )  # fmt: skip
    assert (oi.entering, oi.passed, oi.near, oi.remaining) == (2, 1, 1, 2)
    assert got.coverage.coverage == "COMPLETE" and got.coverage.selected == 4
    assert got.coverage.base == 5  # the delisted one is seen, not selected
    top = got.rows[0]
    assert (top.instrument_id, top.symbol, top.decision, top.classification) == (
        "EQ:AAA", "AAA", "QUALIFIED", "A",
    )  # fmt: skip
    assert top.columns == {"tier": "A"} and [c.outcome for c in top.criteria] == ["PASS", "PASS"]
    assert got.session == DAY and got.user == ALICE and got.screener_id == "draft1"


def test_limit_trims_rows_not_the_summary() -> None:
    got = preview(preview_store(), limit=2)
    assert [r.rank for r in got.rows] == [1, 2] and got.total == 4
    assert sum(got.decisions.values()) == 4


def test_threshold_edits_reuse_the_field_frame_and_a_publish_invalidates() -> None:
    store = preview_store()
    first = preview(store)
    assert not first.cached
    looser = preview(store, criterion(DRAFT, "price", value=30))
    assert looser.cached and looser.decisions["QUALIFIED"] == 2
    assert looser.funnel[0].passed == 3  # ETF1 (40) now passes price
    soft = preview(store, criterion(DRAFT, "price", mode="soft", tolerance=15))
    assert soft.cached and soft.decisions.get("WATCH") == 2
    backend = store.reader._backend  # type: ignore[attr-defined]
    later = T0 + timedelta(minutes=1)
    rows = [{"instrument_id": "EQ:ETF1", "underlying_price": 80.0, "chain_oi": 9000}]
    table = "rollups/instrument/option_liquidity@v1"
    StoreWriter(backend).write_table(
        table, DAY, "f2", stamped(rows, DAY, "f2", later), pending=True
    )
    assert preview(store).cached  # pending: not visible yet
    backend.tables.commit_run("f2", later)
    after = preview(store)
    assert not after.cached and after.funnel[0].passed == 1  # only ETF1 has a row now
    assert preview(store).cached


def test_a_new_field_set_is_a_new_frame() -> None:
    store = preview_store()
    preview(store)
    extra = {**DRAFT, "columns": {**DRAFT["columns"], "oi": f"{LIQ}.chain_oi"}}
    assert preview(store, extra).cached  # chain_oi is already read by a criterion
    more = {**DRAFT, "columns": {"strike": f"{LIQ}.put_strike"}}
    assert not preview(store, more).cached


def test_preview_never_writes() -> None:
    store = preview_store()
    seq, tables = store.reader.visible_seq(), store.reader.table_names()
    preview(store)
    assert store.reader.visible_seq() == seq and store.reader.table_names() == tables
    assert store.configs.names(ALICE, "screeners") == []


@pytest.mark.parametrize(
    ("spec", "path"),
    [
        (criterion(DRAFT, "oi", tolerance=-1), r"criteria\.oi\.tolerance"),
        (criterion(DRAFT, "price", op="near"), r"criteria\.price"),
        (criterion(DRAFT, "price", field="rollup.nope@v1.x"), "criteria: unknown field"),
        ({**DRAFT, "impl": "short_premium_liquidity"}, "impl"),
    ],
)
def test_an_invalid_draft_fails_closed_naming_its_path(spec: dict[str, Any], path: str) -> None:
    with pytest.raises(ConfigurationError, match=path):
        preview(preview_store(), spec)


def test_a_bad_user_or_id_fails() -> None:
    with pytest.raises(ConfigurationError):
        preview_screen(preview_store(), DRAFT, "../etc", on=DAY)
    with pytest.raises(ConfigurationError):
        preview_screen(preview_store(), {**DRAFT, "id": "a b"}, ALICE, on=DAY)


def test_the_session_is_the_latest_stored_one_on_or_before_the_last_closed(
    golden_source: FixtureSource,
) -> None:
    store = api_store(golden_source)[0]
    session, closed = preview_session(store, NOW)
    assert (session, closed) == (END, last_closed_session(NOW))
    later = datetime(2026, 10, 2, 23, tzinfo=UTC)  # nothing stored that late: the latest
    assert preview_session(store, later)[0] == END


def test_the_store_user_is_the_default() -> None:
    store = replace(preview_store(), user=UserContext("bob"))
    assert preview_screen(store, DRAFT, on=DAY, now=T0).user == "bob"


def test_store_over_has_its_own_preview_cache() -> None:
    reader, _ = seeded()
    a = store_over(reader._backend, configs(), UserContext(ALICE))  # type: ignore[attr-defined]
    assert a.preview_cache is not a.cache
