"""``dividend_schedule@v1``: the next ex-dividend date as the partitions stored by the session
knew it. A declared future ex-date is known only from the session that stored it, a past (or
same-day) ex-date is never "next", the amount is split-adjusted to the session, a moved or
withdrawn date is replaced by the latest listing, and a recompute of an earlier session equals
what it knew."""

from datetime import date, timedelta

import pandas as pd
import pytest

from algotrade.features.framework.runner import compute_in_memory
from algotrade.features.registry import GROUPS
from algotrade.features.rollups.corporate import dividend_schedule as ds
from algotrade.features.rollups.price import price_stats
from algotrade.storage.tables.writers import StoreWriter
from tests.helpers.rollup_store import END, series, store, write_bars, write_split
from tests.helpers.stored_frames import stamped

DAY = timedelta(days=1)


def _write(
    writer: StoreWriter,
    stored: date,
    rows: list[tuple[str, date, float]],
    pay: dict[date, object] | None = None,
    kind: str = "recurring",
) -> None:
    """One corporate-actions run stored on ``stored``: (instrument, ex-date, amount)."""
    frame = [
        {
            "instrument_id": iid,
            "symbol": iid[3:],
            "ts": pd.Timestamp(ex, tz="UTC"),
            "cash_amount": amount,
            "distribution_type": kind,
            **({"pay_date": pay[ex]} if pay is not None else {}),
        }
        for iid, ex, amount in rows
    ]
    run = f"div-{stored}-{len(rows)}"
    writer.write_table("events/dividend", stored, run, stamped(frame, stored, run))


def _setup(
    closes: tuple[str, ...] = ("EQ:A", "EQ:B", "EQ:C"),
) -> tuple[StoreWriter, object, list[date]]:
    writer, reader = store()
    days = write_bars(writer, {iid: series(30, i) for i, iid in enumerate(closes)})
    return writer, reader, days


def _frame(reader: object, session: date = END) -> pd.DataFrame | None:
    out = compute_in_memory(reader, [price_stats.GROUP, ds.GROUP], [session])  # type: ignore[arg-type]
    return out[ds.GROUP.key][0].frame


def _rows(reader: object, session: date = END) -> pd.DataFrame:
    frame = _frame(reader, session)
    assert frame is not None
    return frame.set_index("instrument_id")


def test_a_declared_future_ex_date_is_known_only_from_the_session_that_stored_it() -> None:
    writer, reader, days = _setup()
    ex = END + 12 * DAY
    _write(writer, days[-2], [("EQ:A", ex, 0.25)], pay={ex: "2026-11-20"})
    assert _frame(reader, days[-3]) is None  # nothing stored by then: UNKNOWN, no row
    stored_day = _rows(reader, days[-2]).loc["EQ:A"]
    assert stored_day["dividend_status"] == "SCHEDULED" and stored_day["next_ex_date"] == ex
    out = _rows(reader).loc["EQ:A"]
    assert out["next_ex_date"] == ex and out["days_to_ex_date"] == 12
    assert out["next_div_amount"] == pytest.approx(0.25)
    assert out["next_pay_date"] == date(2026, 11, 20)
    assert str(_rows(reader)["next_div_amount"].dtype) == "float32"


def test_a_past_or_same_day_ex_date_is_not_next_and_the_earliest_future_one_is() -> None:
    writer, reader, days = _setup()
    _write(
        writer,
        days[-2],
        [
            ("EQ:A", END - 3 * DAY, 0.20),  # already ex
            ("EQ:A", END, 0.21),  # ex today: bought today, no dividend: not next
            ("EQ:A", END + 20 * DAY, 0.23),
            ("EQ:A", END + 5 * DAY, 0.22),
            ("EQ:B", END, 0.10),  # only an ex-date today: nothing next
        ],
    )
    out = _rows(reader)
    assert (out.loc["EQ:A", "next_ex_date"], out.loc["EQ:A", "days_to_ex_date"]) == (
        END + 5 * DAY,
        5,
    )
    assert out.loc["EQ:A", "next_div_amount"] == pytest.approx(0.22)
    assert out.loc["EQ:B", "dividend_status"] == "NOT_ANNOUNCED"
    assert out.loc["EQ:B", ["next_ex_date", "next_div_amount", "days_to_ex_date"]].isna().all()
    assert out["days_to_ex_date"].dropna().ge(1).all()


def test_the_amount_is_split_adjusted_to_the_session_by_splits_after_its_partition() -> None:
    writer, reader, days = _setup()
    ex = END + 10 * DAY
    _write(writer, days[-6], [("EQ:A", ex, 1.00), ("EQ:B", ex, 1.00), ("EQ:C", ex, 1.00)])
    write_split(writer, "EQ:A", days[-3], 2.0, days[-3])  # after the partition, by the session
    write_split(writer, "EQ:B", days[-6], 5.0, days[-6])  # on the partition's own day: in its terms
    write_split(writer, "EQ:C", END + 2 * DAY, 4.0, END + 2 * DAY)  # after the session: unknown
    out = _rows(reader)
    assert out.loc["EQ:A", "next_div_amount"] == pytest.approx(0.50)
    assert out.loc["EQ:B", "next_div_amount"] == pytest.approx(1.00)
    assert out.loc["EQ:C", "next_div_amount"] == pytest.approx(1.00)
    earlier = _rows(reader, days[-4]).loc["EQ:A"]  # a recompute before the split sees none
    assert earlier["next_div_amount"] == pytest.approx(1.00)


def test_a_restated_amount_and_a_moved_date_follow_the_latest_listing_by_the_session() -> None:
    writer, reader, days = _setup()
    x1, x2 = END + 9 * DAY, END + 16 * DAY
    _write(writer, days[-6], [("EQ:A", x1, 0.30), ("EQ:B", x1, 0.40), ("EQ:C", x1, 0.50)])
    _write(writer, days[-3], [("EQ:A", x1, 0.32), ("EQ:B", x2, 0.40)])  # A restated; B moved
    now, then = _rows(reader), _rows(reader, days[-4])
    assert (now.loc["EQ:A", "next_ex_date"], now.loc["EQ:A", "next_div_amount"]) == (
        x1,
        pytest.approx(0.32),
    )
    assert (now.loc["EQ:B", "next_ex_date"], now.loc["EQ:B", "days_to_ex_date"]) == (x2, 16)
    assert (
        now.loc["EQ:C", "next_ex_date"] == x1
    )  # a later fetch dropping it stores no row to say so
    assert (then.loc["EQ:A", "next_div_amount"], then.loc["EQ:B", "next_ex_date"]) == (
        pytest.approx(0.30),
        x1,
    )  # point in time: a later restatement or move is not known on the earlier session


def test_a_date_the_latest_listing_drops_beside_another_is_ignored() -> None:
    writer, reader, days = _setup()
    x1, x2 = END + 6 * DAY, END + 20 * DAY
    _write(writer, days[-5], [("EQ:A", x1, 0.30), ("EQ:A", x2, 0.31)])
    _write(writer, days[-2], [("EQ:A", x2, 0.31)])  # x1 withdrawn
    out = _rows(reader).loc["EQ:A"]
    assert (out["next_ex_date"], out["next_div_amount"]) == (x2, pytest.approx(0.31))
    assert _rows(reader, days[-3]).loc["EQ:A", "next_ex_date"] == x1  # as it was known then


def test_pay_date_is_null_when_the_source_has_none_and_specials_count() -> None:
    writer, reader, days = _setup()
    ex = END + 7 * DAY
    _write(writer, days[-2], [("EQ:A", ex, 2.0), ("EQ:B", ex, 0.2)], pay={ex: None}, kind="special")
    out = _rows(reader)
    assert pd.isna(out.loc["EQ:A", "next_pay_date"])
    assert out.loc["EQ:A", "dividend_status"] == "SCHEDULED"  # a special is still an ex-date
    assert out.loc["EQ:A", "next_div_amount"] == pytest.approx(2.0)
    writer2, reader2, days2 = _setup()
    _write(writer2, days2[-2], [("EQ:A", ex, 0.2)])  # no pay_date column at all
    assert pd.isna(_rows(reader2).loc["EQ:A", "next_pay_date"])


def test_one_row_per_price_stats_instrument_and_listings_without_a_date_are_not_announced() -> None:
    writer, reader, days = _setup(("EQ:A", "EQ:B"))
    assert _frame(reader) is None  # no dividend partition at all: UNKNOWN, never NOT_ANNOUNCED
    _write(writer, days[-2], [("EQ:A", END - 4 * DAY, 0.1), ("EQ:NOBAR", END + 4 * DAY, 0.1)])
    out = _rows(reader)
    assert list(out.index) == ["EQ:A", "EQ:B"]  # no price_stats row, no schedule row
    assert (out["dividend_status"] == "NOT_ANNOUNCED").all()  # listings read, none upcoming
    assert out.drop(columns="dividend_status").isna().all().all()


def test_a_dividend_declared_after_the_session_is_not_known_in_a_rerun_partition() -> None:
    """A step retried later for the session stores what the vendor knows by then in the
    session's partition: a declaration dated after the session is not known on it."""
    writer, reader, _ = _setup()
    ex = END + 9 * DAY
    frame = pd.DataFrame(
        {
            "instrument_id": ["EQ:A", "EQ:B", "EQ:C"],
            "symbol": ["A", "B", "C"],
            "ts": pd.Timestamp(ex, tz="UTC"),
            "cash_amount": 0.2,
            "declaration_date": [
                (END + 2 * DAY).isoformat(),  # declared after the session: unknown on it
                END.isoformat(),  # declared on it: known
                None,  # the source gives none: kept
            ],
        }
    )
    writer.write_table(
        "events/dividend", END, "rerun", stamped(frame.to_dict("records"), END, "rerun")
    )
    out = _rows(reader)
    assert out["dividend_status"].to_dict() == {
        "EQ:A": "NOT_ANNOUNCED",
        "EQ:B": "SCHEDULED",
        "EQ:C": "SCHEDULED",
    }


def test_a_chunk_of_sessions_equals_each_session_alone() -> None:
    writer, reader, days = _setup()
    x1 = END + 9 * DAY
    _write(writer, days[-5], [("EQ:A", x1, 0.30), ("EQ:B", x1, 0.40)])
    _write(writer, days[-2], [("EQ:A", x1, 0.32)])
    sessions = [days[-6], days[-4], days[-1]]
    chunk = compute_in_memory(reader, [price_stats.GROUP, ds.GROUP], sessions)  # type: ignore[arg-type]
    for result in chunk[ds.GROUP.key]:
        alone = _frame(reader, result.session)
        assert (result.frame is None) == (alone is None)
        if alone is not None:
            pd.testing.assert_frame_equal(result.frame, alone)
    assert chunk[ds.GROUP.key][0].frame is None  # before the first partition
    assert chunk[ds.GROUP.key][2].frame is not None


def test_the_status_explains_the_nulls_and_the_group_is_registered() -> None:
    nxt = ds.GROUP.feature("next_ex_date")
    assert nxt.status_field == "rollup.dividend_schedule@v1.dividend_status"
    assert nxt.explained_statuses == ("NOT_ANNOUNCED",)
    assert ds.GROUP.feature("dividend_status").categories == ("SCHEDULED", "NOT_ANNOUNCED")
    assert GROUPS["dividend_schedule@v1"].table == "rollups/instrument/dividend_schedule@v1"
    assert "events/dividend_declared" in {i.table for i in ds.GROUP.inputs}
