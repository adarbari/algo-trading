"""``fundamentals@v2``: point in time by filing date, cover count vs weighted fallback,
amendments, splits after the count, statuses (OK / NO_SHARES / STALE / NO_PRICE), and the
selectable catalogue fields."""

from dataclasses import replace
from datetime import date, timedelta

import pandas as pd
import pytest

from algotrade.core.model.fields import field_source
from algotrade.features.framework.runner import compute_in_memory
from algotrade.features.registry import catalogue_columns
from algotrade.features.rollups import price_stats
from algotrade.features.rollups.fundamentals import GROUP, FundamentalsParams, choose
from algotrade.features.site import site_features
from algotrade.storage.configs.files import FileConfigStore
from algotrade.storage.tables.writers import StoreWriter
from tests.conftest import REPO_ROOT
from tests.helpers.rollup_store import END, series, store, write_bars, write_split
from tests.helpers.stored_frames import stamped

STORED = END + timedelta(days=1)  # a backfill stored after every session it serves


def fact(iid: str, concept: str, shares: float, end: date, filed: date, form: str = "10-Q"):  # type: ignore[no-untyped-def]
    return {
        "instrument_id": iid, "symbol": iid[3:], "cik": "0000000001", "concept": concept,
        "period_end": end, "filed": filed, "form": form, "accn": f"{iid}-{filed}-{form}",
        "shares": shares, "fetched_on": STORED,
    }  # fmt: skip


def write_facts(writer: StoreWriter, rows: list[dict[str, object]]) -> None:
    writer.write_table("instruments/shares", STORED, "facts", stamped(rows, STORED, "facts"))


def _setup() -> tuple[object, list[date]]:
    writer, reader = store()
    closes = {iid: series(60, n) for n, iid in enumerate(["EQ:A", "EQ:W", "EQ:ETF", "EQ:OLD"])}
    days = write_bars(writer, closes)
    write_facts(
        writer,
        [
            fact("EQ:A", "dei", 1000.0, END - timedelta(days=80), END - timedelta(days=75)),
            fact(
                "EQ:A", "weighted_basic", 990.0, END - timedelta(days=95), END - timedelta(days=75)
            ),
            # an amendment of the same cover count, filed later
            fact(
                "EQ:A", "dei", 1001.0, END - timedelta(days=80), END - timedelta(days=60), "10-Q/A"
            ),
            # filed AFTER the earlier session below, though stored before the backfill ran
            fact("EQ:A", "dei", 1100.0, END - timedelta(days=12), END - timedelta(days=10)),
            # W stopped tagging the cover page: the weighted average is newer
            fact("EQ:W", "dei", 50.0, END - timedelta(days=900), END - timedelta(days=890)),
            fact(
                "EQ:W", "weighted_basic", 70.0, END - timedelta(days=40), END - timedelta(days=20)
            ),
            fact("EQ:OLD", "dei", 7.0, END - timedelta(days=500), END - timedelta(days=495)),
            fact("EQ:GONE", "dei", 9.0, END - timedelta(days=30), END - timedelta(days=25)),
        ],
    )
    write_split(writer, "EQ:A", END - timedelta(days=5), 2.0, END)  # after the 1100 count
    return reader, days


def _rows(reader: object, sessions: list[date], params: FundamentalsParams | None = None):  # type: ignore[no-untyped-def]
    by_key = {GROUP.key: params} if params else None
    out = compute_in_memory(reader, [price_stats.GROUP, GROUP], sessions, by_key)  # type: ignore[arg-type]
    return {r.session: r.frame.set_index("instrument_id") for r in out[GROUP.key]}


def _market_cap(reader: object) -> pd.Series:
    """The ``market_cap`` expression feature over this session's computed groups."""
    out = compute_in_memory(reader, [price_stats.GROUP, GROUP], [END])  # type: ignore[arg-type]
    frames = {
        g.table: out[g.key][0].frame.assign(session_date=END)  # type: ignore[union-attr]
        for g in (price_stats.GROUP, GROUP)
    }
    fs = site_features(FileConfigStore(REPO_ROOT / "config"))
    return fs.evaluate(frames, ["market_cap"]).set_index("instrument_id")["market_cap"]


def test_statuses_and_market_cap() -> None:
    reader, _ = _setup()
    rows = _rows(reader, [END])[END]
    rows["market_cap"] = _market_cap(reader)
    a = rows.loc["EQ:A"]
    close_a = series(60, 0)[-1]
    assert a["market_cap_status"] == "OK" and a["shares_source"] == "dei"
    assert a["shares_outstanding"] == pytest.approx(2200.0)  # 1100 x the 2:1 split after it
    assert a["market_cap"] == pytest.approx(2200.0 * close_a, rel=1e-6)
    assert (a["shares_as_of"], a["shares_filed"]) == (
        END - timedelta(days=12),
        END - timedelta(days=10),
    )
    w = rows.loc["EQ:W"]
    assert (w["shares_source"], w["shares_outstanding"], w["market_cap_status"]) == (
        "weighted_basic",
        70.0,
        "OK",
    )
    etf = rows.loc["EQ:ETF"]
    assert etf["market_cap_status"] == "NO_SHARES" and pd.isna(etf["market_cap"])
    assert pd.isna(etf["shares_outstanding"]) and pd.isna(etf["shares_source"])
    old = rows.loc["EQ:OLD"]
    assert (old["market_cap_status"], old["shares_outstanding"]) == ("STALE", 7.0)
    assert pd.isna(old["market_cap"])
    gone = rows.loc["EQ:GONE"]
    assert gone["market_cap_status"] == "NO_PRICE" and pd.isna(gone["market_cap"])
    loose = _rows(reader, [END], FundamentalsParams(stale_days=600))[END]
    assert loose.loc["EQ:OLD", "market_cap_status"] == "OK"


def test_point_in_time_by_filing_date() -> None:
    reader, days = _setup()
    earlier = days[-20]  # after the amendment, before the 1100 count was filed
    rows = _rows(reader, [earlier, END])
    a = rows[earlier].loc["EQ:A"]
    assert a["shares_outstanding"] == 1001.0  # the amended count, no split yet
    assert a["shares_filed"] == END - timedelta(days=60)
    before_amendment = days[-50]
    first = _rows(reader, [before_amendment])[before_amendment].loc["EQ:A"]
    assert first["shares_outstanding"] == 1000.0
    w = rows[earlier].loc["EQ:W"]
    assert w["shares_source"] == "dei" and w["market_cap_status"] == "STALE"


def test_choose_prefers_the_cover_count_while_it_is_still_filed() -> None:
    day = date(2026, 1, 1)
    facts = pd.DataFrame(
        [
            fact("EQ:X", "dei", 10.0, day, day),
            fact("EQ:X", "weighted_basic", 9.0, day - timedelta(days=30), day),
            fact("EQ:Y", "weighted_basic", 5.0, day, day),
        ]
    )
    chosen = choose(facts).set_index("instrument_id")
    assert (
        chosen.loc["EQ:X", "concept"] == "dei" and chosen.loc["EQ:Y", "concept"] == "weighted_basic"
    )
    assert choose(None).empty


def test_params_validate_and_catalogue_fields() -> None:
    with pytest.raises(ValueError, match="stale_days"):
        replace(FundamentalsParams(), stale_days=0)
    columns = catalogue_columns()["fundamentals@v2"]
    assert columns["shares_outstanding"] == "float32" and columns["market_cap_status"] == "str"
    assert "market_cap" not in columns  # an expression feature since v2
    assert field_source("rollup.fundamentals@v2.market_cap_status") == (
        "rollups/instrument/fundamentals@v2",
        "market_cap_status",
    )
