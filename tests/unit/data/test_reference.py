"""The one snapshot rule and the reference reads built on it (``algotrade.data.reference``)."""

from datetime import UTC, date, datetime, timedelta

import pandas as pd
import pytest

from algotrade.core.model.errors import MissingDataError
from algotrade.data import StoreReader
from algotrade.data.reference import (
    IBKR_CONTRACTS,
    companies,
    company_sectors,
    descriptions,
    ibkr_contracts,
    instrument_terms,
    instrument_view,
    instruments,
    load_universe,
    resolver,
    snapshot,
    stored_descriptions,
)
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.tables.writers import StoreWriter
from tests.helpers.stored_frames import T0, stamped, universe_rows

D1, D2 = date(2026, 10, 1), date(2026, 10, 2)
REF = "instruments/reference"


def reference(symbols: dict[str, str], **extra: object) -> list[dict[str, object]]:
    return [
        {
            "instrument_id": iid,
            "symbol": symbol,
            "asset_class": "EQ",
            "security_type": "COMMON_STOCK",
            "multiplier": 1.0,
            "status": "ACTIVE",
            **extra,
        }
        for symbol, iid in symbols.items()
    ]


def store() -> tuple[StoreWriter, StoreReader]:
    backend = MemoryBackend()
    return StoreWriter(backend), StoreReader(backend)


def test_snapshot_is_on_or_before_else_the_earliest() -> None:
    writer, reader = store()
    assert snapshot(reader, REF, D1) is None  # nothing stored at all
    writer.write_table(REF, D1, "r1", stamped(reference({"A": "EQ:A"}), D1, "r1"))
    writer.write_table(REF, D2, "r2", stamped(reference({"A": "EQ:A"}), D2, "r2"))
    on = snapshot(reader, REF, D1)
    assert on is not None and (on.snapshot_date, on.pre_snapshot) == (D1, False)
    after = snapshot(reader, REF, D2 + timedelta(days=9))
    assert after is not None and (after.snapshot_date, after.pre_snapshot) == (D2, False)
    early = snapshot(reader, REF, D1 - timedelta(days=30))
    assert early is not None and (early.snapshot_date, early.pre_snapshot) == (D1, True)
    latest = snapshot(reader, REF)
    assert latest is not None and (latest.snapshot_date, latest.pre_snapshot) == (D2, False)


def test_instruments_and_terms_follow_the_rule() -> None:
    writer, reader = store()
    with pytest.raises(MissingDataError, match="no snapshot stored"):
        instruments(reader, D1)
    rows = [
        *reference({"A": "EQ:A"}),
        {
            "instrument_id": "FUT:ESZ6",
            "symbol": "ESZ6",
            "asset_class": "FUT",
            "security_type": "FUTURE",
            "multiplier": 50.0,
            "status": "ACTIVE",
            "tick_size": 0.25,
        },
    ]
    writer.write_table(REF, D1, "r1", stamped(rows, D1, "r1"))
    writer.write_table(REF, D2, "r2", stamped(reference({"A2": "EQ:A"}), D2, "r2"))
    assert list(instruments(reader, D1)["symbol"]) == ["A", "ESZ6"]
    assert list(instruments(reader, D2 + timedelta(days=5))["symbol"]) == ["A2"]
    assert list(instruments(reader, D1 - timedelta(days=1))["symbol"]) == ["A", "ESZ6"]
    terms = instrument_terms(reader, D1)
    assert terms["FUT:ESZ6"].multiplier == 50.0
    assert terms["FUT:ESZ6"].tick_size == 0.25
    assert terms["EQ:A"].tick_size == 0.01
    with pytest.raises(MissingDataError, match="not known at"):  # the version pin
        instruments(reader, D1, as_of=T0 - timedelta(days=1))


def test_companies_follow_the_snapshot_rule() -> None:
    writer, reader = store()
    company = "instruments/company"
    assert companies(reader, D1) is None  # no company snapshot at all
    rows = [
        {"instrument_id": f"EQ:{s}", "symbol": s, "cik": "1", "name": f"{s} Inc", "sic": "3571",
         "sector": "Technology", "fetched_on": D2}
        for s in ("A", "B")
    ]  # fmt: skip
    writer.write_table(company, D2, "c2", stamped(rows, D2, "c2"))
    assert companies(reader, D1, ["EQ:A"]) is None  # a later snapshot never stands in
    found = companies(reader, D2, ["EQ:A"])
    assert found is not None and list(found["name"]) == ["A Inc"]
    every = companies(reader, D2 + timedelta(days=3))
    assert every is not None and len(every) == 2


def test_company_sectors_are_the_snapshot_on_or_before_with_three_columns() -> None:
    writer, reader = store()
    company = "instruments/company"
    assert company_sectors(reader, D2) is None  # no company snapshot at all
    rows = [
        {"instrument_id": f"EQ:{s}", "symbol": s, "cik": "1", "name": f"{s} Inc", "sic": "3571",
         "sector": sector, "industry": "Software", "fetched_on": D2}
        for s, sector in (("A", "Technology"), ("B", None))
    ]  # fmt: skip
    writer.write_table(company, D2, "c2", stamped(rows, D2, "c2"))
    assert company_sectors(reader, D1) is None  # taken after the session: not known then
    found = company_sectors(reader, D2 + timedelta(days=3))
    assert found is not None and list(found.columns) == ["instrument_id", "sector", "industry"]
    assert found["sector"].iloc[0] == "Technology" and pd.isna(found["sector"].iloc[1])


def test_instrument_view_joins_reference_and_session_rollups() -> None:
    writer, reader = store()
    writer.write_table(REF, D1, "r1", stamped(reference({"A": "EQ:A", "B": "EQ:B"}), D1, "r1"))
    liq = [{"instrument_id": "EQ:A", "put_tier": "A"}]
    writer.write_table("rollups/instrument/liq@v1", D2, "r2", stamped(liq, D2, "r2"))
    fields = ["instrument.symbol", "rollup.liq@v1.put_tier", "rollup.other@v1.x"]
    view = instrument_view(reader, D2, fields)
    assert (view.reference_snapshot, view.pre_snapshot) == (D1, False)
    assert view.missing == ("rollups/instrument/other@v1",)
    rows = view.frame.set_index("instrument_id")
    assert rows.loc["EQ:A", "rollup.liq@v1.put_tier"] == "A"
    assert pd.isna(rows.loc["EQ:B", "rollup.liq@v1.put_tier"])
    everything = instrument_view(reader, D2)
    assert {"instrument.symbol", "instrument.multiplier"} <= set(everything.frame.columns)
    assert instrument_view(reader, D1, ["rollup.liq@v1.put_tier"]).missing == (
        "rollups/instrument/liq@v1",
    )  # a rollup is read for the session only, never stale


def test_instrument_view_flags_a_company_snapshot_taken_after_the_session() -> None:
    writer, reader = store()
    writer.write_table(REF, D1, "r1", stamped(reference({"A": "EQ:A"}), D1, "r1"))
    company = [{"instrument_id": "EQ:A", "symbol": "A", "cik": "1", "name": "A Inc",
                "sic": "3571", "sector": "Technology", "fetched_on": D2}]  # fmt: skip
    writer.write_table("instruments/company", D2, "c2", stamped(company, D2, "c2"))
    assert instrument_view(reader, D1, ["instrument.sector"]).company_pre_snapshot is True
    assert instrument_view(reader, D2, ["instrument.sector"]).company_pre_snapshot is False


def test_instrument_view_before_the_first_snapshot_flags_survivorship() -> None:
    writer, reader = store()
    writer.write_table(REF, D2, "r2", stamped(reference({"A": "EQ:A"}), D2, "r2"))
    view = instrument_view(reader, D1, ["instrument.symbol"])
    assert (view.reference_snapshot, view.pre_snapshot) == (D2, True)
    assert list(view.frame["instrument_id"]) == ["EQ:A"]


def test_universe_uses_the_same_rule() -> None:
    writer, reader = store()
    with pytest.raises(MissingDataError, match="universe import"):
        load_universe(reader, D1)
    writer.write_table("universe", D2, "u", stamped(universe_rows(["AAPL"]), D2, "u"))
    early = load_universe(reader, D1)
    assert (early.snapshot_date, early.pre_snapshot) == (D2, True)
    on_time = load_universe(reader, D2 + timedelta(days=1))
    assert (on_time.snapshot_date, on_time.pre_snapshot) == (D2, False)
    assert on_time.instruments == ["EQ:AAPL"]


def test_resolver_uses_the_reference_as_of_the_session() -> None:
    writer, reader = store()
    assert resolver(reader, D1).id_for("aapl") == "EQ:AAPL"  # no reference yet: symbol ids
    day1 = reference({"FB": "EQ:BBG1"}) + reference({"OLDCO": "EQ:OLDCO"}, status="DELISTED")
    day2 = reference({"META": "EQ:BBG1"}) + reference({"FB": "EQ:OLDCO"}, status="DELISTED")
    writer.write_table(REF, D1, "r1", stamped(day1, D1, "r1"))
    writer.write_table(REF, D2, "r2", stamped(day2, D2, "r2"))
    assert resolver(reader, D1).id_for("FB") == "EQ:BBG1"
    assert resolver(reader, D1 - timedelta(days=30)).snapshot == D1  # backfill: earliest
    later = resolver(reader, D2 + timedelta(days=3))
    assert later.snapshot == D2
    assert later.id_for("META") == "EQ:BBG1"
    assert later.id_for("FB") == "EQ:OLDCO"  # only a delisted row has it now
    assert later.symbol_for("EQ:BBG1") == "META"
    frame, unknown = later.resolve(pd.DataFrame({"symbol": ["meta", "NEW"], "x": [1, 2]}))
    assert list(frame["instrument_id"]) == ["EQ:BBG1", "EQ:NEW"] and unknown == 1


def test_ibkr_contracts_are_the_snapshot_on_or_before_never_a_later_one() -> None:
    writer, reader = store()
    assert ibkr_contracts(reader, D2) is None
    rows = [{"instrument_id": "EQ:A", "symbol": "A", "conid": 265598, "resolved_at": D2}]
    writer.write_table(IBKR_CONTRACTS, D2, "c", stamped(rows, D2, "c"))
    found = ibkr_contracts(reader, D2 + timedelta(days=3))
    assert found is not None and list(found["conid"]) == [265598]
    assert ibkr_contracts(reader, D1) is None  # resolved later: not known on D1


# ----------------------------------------------------------------- descriptions (increments)
DESC = "instruments/description"
T1, T2 = datetime(2026, 9, 1, 22, tzinfo=UTC), datetime(2026, 10, 1, 22, tzinfo=UTC)


def described(symbol: str, text: str | None, fetched: date) -> dict[str, object]:
    return {
        "instrument_id": f"EQ:{symbol}", "symbol": symbol, "description": text,
        "description_source": "massive_overview", "fetched_on": fetched,
    }  # fmt: skip


def test_descriptions_of_an_empty_store() -> None:
    reader = StoreReader(MemoryBackend())
    assert stored_descriptions(reader).empty and descriptions(reader).empty


def test_descriptions_union_latest_row_markers_and_point_in_time() -> None:
    writer = StoreWriter(MemoryBackend())
    first = [
        described("AAA", "Old text.", D1),
        described("BBB", None, D1),
        described("ETF", "Seeks.", D1),
    ]
    writer.write_table(DESC, D1, "r1", stamped(first, D1, "r1", T1))
    second = [described("AAA", "New text.", D2), described("CCC", "Third.", D2)]
    writer.write_table(DESC, D2, "r2", stamped(second, D2, "r2", T2))
    reader = StoreReader(writer._backend)
    stored = stored_descriptions(reader).set_index("symbol")
    assert list(stored.index) == ["AAA", "BBB", "CCC", "ETF"]
    assert stored.loc["AAA", "description"] == "New text."  # the latest run wins
    assert stored.loc["AAA", "fetched_on"] == D2 and stored.loc["BBB", "fetched_on"] == D1
    assert "knowledge_ts" not in stored.columns and "run_id" not in stored.columns
    texts = descriptions(reader).set_index("symbol")
    assert list(texts.index) == ["AAA", "CCC", "ETF"]  # BBB is a marker: nothing to show
    assert list(descriptions(reader, ["EQ:ETF"])["symbol"]) == ["ETF"]
    then = descriptions(reader, as_of=datetime(2026, 9, 15, tzinfo=UTC)).set_index("symbol")
    assert then.loc["AAA", "description"] == "Old text." and "CCC" not in then.index
