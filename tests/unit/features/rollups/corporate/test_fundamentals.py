"""``fundamentals@v3``: point in time by filing date, cover count vs weighted fallback,
amendments, splits after the count, statuses (OK / NO_SHARES / STALE / NO_PRICE), the count a
year earlier (``shares_outstanding_year_ago``: the 9 to 15 month window, the same concept, point
in time by filing date, split-adjusted), ``shares_change_yoy``, that every v2 column is
unchanged, and the selectable catalogue fields."""

from dataclasses import replace
from datetime import date, timedelta

import pandas as pd
import pytest

from algotrade.core.model.fields import field_source
from algotrade.features.framework.runner import compute_in_memory
from algotrade.features.registry import catalogue_columns
from algotrade.features.rollups.corporate.fundamentals import (
    GROUP,
    FundamentalsParams,
    choose,
    year_ago,
)
from algotrade.features.rollups.price import price_stats
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
        "period_start": None, "period_end": end, "filed": filed, "form": form,
        "accn": f"{iid}-{filed}-{form}", "shares": shares, "fetched_on": STORED,
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


# What fundamentals@v2 computed for the facts of ``_setup`` (recorded from the v2 module before it
# was replaced; dates as ISO strings): every v3 column that existed in v2 stays identical.
V2_COLUMNS = (
    "shares_outstanding", "shares_as_of", "shares_filed", "shares_source", "market_cap_status",
)  # fmt: skip
# fmt: off
V2_END = {
    "EQ:A": (2200.0, "2026-09-20", "2026-09-22", "dei", "OK"),
    "EQ:ETF": (None, None, None, None, "NO_SHARES"),
    "EQ:GONE": (9.0, "2026-09-02", "2026-09-07", "dei", "NO_PRICE"),
    "EQ:OLD": (7.0, "2025-05-20", "2025-05-25", "dei", "STALE"),
    "EQ:W": (70.0, "2026-08-23", "2026-09-12", "weighted_basic", "OK"),
}

V2_EARLY = {
    "EQ:A": (1001.0, "2026-07-14", "2026-08-03", "dei", "OK"),
    "EQ:ETF": (None, None, None, None, "NO_SHARES"),
    "EQ:OLD": (7.0, "2025-05-20", "2025-05-25", "dei", "STALE"),
    "EQ:W": (50.0, "2024-04-15", "2024-04-25", "dei", "STALE"),
}

# fmt: on


def _recorded(rows: pd.DataFrame) -> dict[str, tuple[object, ...]]:
    def plain(value: object) -> object:
        if value is None or (not isinstance(value, str | date) and pd.isna(value)):
            return None
        return value.isoformat() if isinstance(value, date) else value

    return {iid: tuple(plain(row[c]) for c in V2_COLUMNS) for iid, row in rows.iterrows()}


def test_every_v2_column_is_unchanged() -> None:
    reader, days = _setup()
    earlier = days[-20]
    out = _rows(reader, [earlier, END])
    assert _recorded(out[END]) == V2_END
    assert _recorded(out[earlier]) == V2_EARLY
    assert out[END]["shares_outstanding_year_ago"].isna().all()  # no count a year back in _setup


def _year_ago_store() -> tuple[object, list[date]]:
    """Counts as of ``AS_OF`` (END - 90 days) with older ones at known distances before it."""
    writer, reader = store()
    names = ["EQ:Y", "EQ:W", "EQ:SPL", "EQ:PIT", "EQ:NEW", "EQ:OUT"]
    days = write_bars(writer, {n: series(60, i) for i, n in enumerate(names)})
    ago = lambda n: AS_OF - timedelta(days=n)  # noqa: E731
    filed = lambda end: end + timedelta(days=5)  # noqa: E731
    # The current cover counts are amended last (``choose`` takes the latest filing), after the
    # amendments of the older counts below.
    rows = [
        *(fact(n, "dei", 1000.0, AS_OF, FILED) for n in ("EQ:Y", "EQ:NEW")),
        *(
            fact(n, "dei", 1000.0, AS_OF, END - timedelta(days=20), "10-Q/A")
            for n in ("EQ:Y", "EQ:PIT")
        ),
        # Y: 700 is older than 15 months, 800 is 400 days back, 900 is 360 (closest to a year,
        # amended to 905 later), 950 is under 9 months back
        fact("EQ:Y", "dei", 700.0, ago(500), filed(ago(500))),
        fact("EQ:Y", "dei", 800.0, ago(400), filed(ago(400))),
        fact("EQ:Y", "dei", 900.0, ago(360), filed(ago(360))),
        fact("EQ:Y", "dei", 905.0, ago(360), END - timedelta(days=30), "10-Q/A"),
        fact("EQ:Y", "dei", 950.0, ago(200), filed(ago(200))),
        fact("EQ:Y", "weighted_basic", 111.0, ago(365), filed(ago(365))),  # another concept
        # W: only the weighted average is current; the cover count a year back is not used
        fact("EQ:W", "weighted_basic", 70.0, AS_OF, FILED),
        fact("EQ:W", "weighted_basic", 60.0, ago(366), filed(ago(366))),
        fact("EQ:W", "dei", 999.0, ago(365), filed(ago(365))),
        # SPL: 500 shares 440 days back, a 2:1 split 430 days back (before the 1100 count)
        fact("EQ:SPL", "dei", 1100.0, AS_OF, FILED),
        fact("EQ:SPL", "dei", 500.0, ago(440), filed(ago(440))),
        # PIT: 800 is amended to 810 after the earlier session
        fact("EQ:PIT", "dei", 1000.0, AS_OF, FILED),
        fact("EQ:PIT", "dei", 800.0, ago(365), AS_OF - timedelta(days=360)),
        fact("EQ:PIT", "dei", 810.0, ago(365), END - timedelta(days=30), "10-Q/A"),
        # NEW: a recent filer; OUT: its only older count is 20 months back
        fact("EQ:OUT", "dei", 1000.0, AS_OF, FILED),
        fact("EQ:OUT", "dei", 600.0, ago(600), filed(ago(600))),
    ]
    write_facts(writer, rows)
    write_split(writer, "EQ:SPL", ago(430), 2.0, END)
    return reader, days


AS_OF = END - timedelta(days=90)
FILED = AS_OF + timedelta(days=5)


def test_the_count_a_year_earlier_is_the_closest_one_of_the_same_kind() -> None:
    reader, _ = _year_ago_store()
    rows = _rows(reader, [END])[END]
    assert rows.loc["EQ:Y", "shares_outstanding_year_ago"] == 905.0  # not 700, 800, 950, 111
    assert rows.loc["EQ:W", "shares_outstanding_year_ago"] == 60.0  # the weighted one
    assert rows.loc["EQ:W", "shares_source"] == "weighted_basic"
    assert pd.isna(rows.loc["EQ:NEW", "shares_outstanding_year_ago"])  # no count a year back
    assert pd.isna(rows.loc["EQ:OUT", "shares_outstanding_year_ago"])  # 20 months is too old
    assert rows.loc["EQ:Y", "shares_outstanding"] == 1000.0  # the current count is unchanged


def test_the_year_ago_count_is_split_adjusted_to_the_session() -> None:
    """A 2:1 split between the two counts: 500 then is 1000 now, so 1100 is +10%, not +120%."""
    reader, _ = _year_ago_store()
    spl = _rows(reader, [END])[END].loc["EQ:SPL"]
    assert (spl["shares_outstanding"], spl["shares_outstanding_year_ago"]) == (1100.0, 1000.0)


def test_the_year_ago_count_is_point_in_time_by_filing_date() -> None:
    reader, days = _year_ago_store()
    earlier = max(d for d in days if d <= END - timedelta(days=40))  # the amendment is ahead
    out = _rows(reader, [earlier, END])
    assert out[earlier].loc["EQ:PIT", "shares_outstanding_year_ago"] == 800.0
    assert out[END].loc["EQ:PIT", "shares_outstanding_year_ago"] == 810.0  # the amendment counts


def test_year_ago_is_empty_without_facts_or_counts() -> None:
    chosen = choose(pd.DataFrame([fact("EQ:X", "dei", 10.0, END, END)]))
    assert year_ago(None, chosen).empty and year_ago(pd.DataFrame(), chosen).empty
    assert year_ago(pd.DataFrame([fact("EQ:X", "dei", 10.0, END, END)]), chosen).empty


def test_shares_change_yoy_end_to_end_on_stored_counts() -> None:
    reader, _ = _year_ago_store()
    out = compute_in_memory(reader, [price_stats.GROUP, GROUP], [END])
    frames = {
        g.table: out[g.key][0].frame.assign(session_date=END)  # type: ignore[union-attr]
        for g in (price_stats.GROUP, GROUP)
    }
    fs = site_features(FileConfigStore(REPO_ROOT / "config"))
    change = fs.evaluate(frames, ["shares_change_yoy"]).set_index("instrument_id")
    change = change["shares_change_yoy"]
    assert change["EQ:Y"] == pytest.approx(1000 / 905 - 1)  # dilution
    assert change["EQ:SPL"] == pytest.approx(0.1)
    assert change["EQ:PIT"] == pytest.approx(1000 / 810 - 1)
    assert change["EQ:W"] == pytest.approx(70 / 60 - 1)
    assert change[["EQ:NEW", "EQ:OUT"]].isna().all()


def test_params_validate_and_catalogue_fields() -> None:
    with pytest.raises(ValueError, match="stale_days"):
        replace(FundamentalsParams(), stale_days=0)
    columns = catalogue_columns()["fundamentals@v3"]
    assert columns["shares_outstanding"] == "float32" and columns["market_cap_status"] == "str"
    assert columns["shares_outstanding_year_ago"] == "float32"
    assert "market_cap" not in columns  # an expression feature since v2
    assert field_source("rollup.fundamentals@v3.market_cap_status") == (
        "rollups/instrument/fundamentals@v3",
        "market_cap_status",
    )
