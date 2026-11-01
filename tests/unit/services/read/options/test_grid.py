"""The option grid of an underlying for exactly the session: cells at our delta bands and
expiry buckets with derived figures only (no vendor quote on any type), the pick shared with
``short_premium@v1`` (the (0.20, 30-day) cell is the group's row), and every UNKNOWN case with
its code: no partition, no row, not optionable, no spot, no expiry, a duplicate expiry, a
one-sided chain, no strike near a band, an unknown report date, an IV rank still provisional."""

import dataclasses
import math
from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from algotrade.features.rollups.options.iv30 import DIVIDENDS, OPTIONS, RATES, UNDERLYINGS
from algotrade.features.rollups.premium import short_premium
from algotrade.quant.black_scholes import price
from algotrade.services.read.options import grid as grid_module
from algotrade.services.read.options.grid import GridCell, OptionGrid, load_option_grid
from algotrade.services.read.values import Unknown, UnknownCode
from algotrade.storage.tables.writers import StoreWriter
from tests.helpers.rollup_store import chain_rows, quote_row, write_chains, write_curve, write_rows
from tests.unit.services.read.instruments.conftest import D0, D1, context, store_with

AAA, ETF = "EQ:AAA", "EQ:ETFX"
DIVIDENDS_TABLE = "rollups/instrument/div_yield@v1"
R = 0.03
BUCKETS = (7, 14, 30, 45, 60, 90)
EXPIRIES = {D1 + timedelta(days=d): 0.25 for d in BUCKETS}
STRIKES = tuple(float(k) for k in np.arange(70.0, 130.5, 0.5))  # a fine ladder: every band has one
FORBIDDEN = {"bid", "ask", "last", "size", "bid_size", "ask_size", "volume"}


def chain(writer: StoreWriter, vols: dict[date, float] | None = None, **kw: object) -> None:
    rows = chain_rows(AAA, D1, 100.0, vols or EXPIRIES, R, strikes=STRIKES)
    write_chains(writer, D1, rows, {AAA: 100.0})
    write_curve(writer, D1, R)


def grid(*writes: object, user_day: date | None = None) -> OptionGrid | Unknown:
    reader = store_with(*writes)  # type: ignore[arg-type]
    return load_option_grid(context(reader, user_day), AAA)


def good(found: OptionGrid | Unknown) -> OptionGrid:
    assert isinstance(found, OptionGrid), found
    return found


def test_a_grid_has_a_cell_per_expiry_bucket_and_band_for_each_right() -> None:
    g = good(grid(chain))
    assert g.bands == (0.10, 0.15, 0.20, 0.25, 0.30)
    assert [c.bucket for c in g.columns] == list(BUCKETS)
    assert [c.days for c in g.columns] == list(BUCKETS)
    assert len(g.puts) == len(g.calls) == 6 and all(len(row) == 5 for row in g.puts + g.calls)
    assert all(isinstance(cell, GridCell) for row in g.puts + g.calls for cell in row)
    assert (g.priced_at, g.session, g.underlying_id) == (100.0, D1, AAA)


def test_a_cell_is_the_contract_nearest_the_band_with_the_figures_of_a_sold_option() -> None:
    g = good(grid(chain))
    put = g.puts[2][2]  # 30 days, 0.20 delta
    assert isinstance(put, GridCell)
    assert put.delta < 0 and abs(abs(put.delta) - 0.20) <= 0.025
    assert put.iv == pytest.approx(0.25, abs=1e-5)  # the vol the chain was priced at
    expected = float(price(100.0, put.strike, 30 / 365, R, 0.0, 0.25, False))
    assert put.mid == pytest.approx(expected, abs=0.011)  # the mid of a bid / ask 0.02 wide
    assert put.roc == pytest.approx(put.mid / put.strike)
    assert put.yield_ann == pytest.approx(put.roc * 365 / 30)
    assert put.breakeven == pytest.approx(put.strike - put.mid)
    assert 0 < put.p_below < 0.5 and put.spread_pct > 0 and put.open_interest == 500
    call = g.calls[2][2]
    assert isinstance(call, GridCell) and call.delta > 0
    assert call.roc == pytest.approx(call.mid / 100.0)
    assert call.breakeven == pytest.approx(100.0 - call.mid)


def test_a_higher_delta_band_is_nearer_the_money() -> None:
    g = good(grid(chain))
    puts = [c.strike for c in g.puts[2] if isinstance(c, GridCell)]
    calls = [c.strike for c in g.calls[2] if isinstance(c, GridCell)]
    assert puts == sorted(puts) and calls == sorted(calls, reverse=True)  # 0.10 is farthest out


def test_no_type_of_the_grid_carries_a_vendor_quote_field() -> None:
    for cls in (OptionGrid, grid_module.GridExpiry, GridCell):
        names = {f.name for f in dataclasses.fields(cls)}
        assert not names & FORBIDDEN, (cls.__name__, names & FORBIDDEN)


def with_yield(value: float | None) -> object:
    """The chain plus a stored dividend yield (None: no row; NaN: a row with a null yield)."""

    def write(writer: StoreWriter) -> None:
        chain(writer)
        if value is not None:
            row = {"instrument_id": AAA, "div_yield": value}
            write_rows(writer, "rollups/instrument/div_yield@v1", D1, [row])

    return write


@pytest.mark.parametrize("stored", [None, 0.02, float("nan")], ids=["no row", "0.02", "null"])
def test_the_030_day_cell_at_020_delta_is_the_short_premium_row(stored: float | None) -> None:
    write = with_yield(stored)
    g = good(grid(write))
    rows = write_and_compute(write)
    assert g.q_known is (stored is not None and not math.isnan(stored))
    assert rows["premium_status"] == "OK"  # a null yield priced with 0, as the grid does
    for side, cells in (("put", g.puts), ("call", g.calls)):
        cell = cells[2][2]
        assert isinstance(cell, GridCell)
        assert rows[f"{side}_strike"] == cell.strike
        assert rows[f"{side}_breakeven"] == pytest.approx(cell.breakeven)
        assert rows[f"{side}_yield_ann"] == pytest.approx(cell.yield_ann)
    assert rows["target_expiry"] == g.columns[2].expiry


def test_a_null_open_interest_is_none_never_zero() -> None:
    def no_oi(writer: StoreWriter) -> None:
        rows = chain_rows(AAA, D1, 100.0, EXPIRIES, R, strikes=STRIKES)
        for row in rows:
            row["open_interest"] = None
        write_chains(writer, D1, rows, {AAA: 100.0})
        write_curve(writer, D1, R)

    g = good(grid(no_oi))
    cells = [c for row in g.puts + g.calls for c in row if isinstance(c, GridCell)]
    assert cells and all(c.open_interest is None for c in cells)


def write_and_compute(write: object) -> pd.Series:
    reader = store_with(write)  # type: ignore[arg-type]
    options = reader.table("chains/option_quotes", D1)
    quotes = reader.table("chains/underlying_quotes", D1)
    curve = reader.table("rates/treasury", D1)
    dividends = reader.table(DIVIDENDS_TABLE, D1)
    assert options is not None and quotes is not None and curve is not None
    inputs = {
        OPTIONS: options,
        RATES: curve,
        UNDERLYINGS: quotes,
        DIVIDENDS: dividends,
    }
    row = short_premium.compute(inputs, D1, None).set_index("instrument_id").loc[AAA]
    assert isinstance(row, pd.Series)
    return row


def test_no_chain_partition_for_the_session_is_no_partition_never_an_older_one() -> None:
    def old(writer: StoreWriter) -> None:
        write_chains(writer, D0, chain_rows(AAA, D0, 100.0, EXPIRIES, R), {AAA: 100.0})
        write_curve(writer, D0, R)

    found = grid(old)
    assert isinstance(found, Unknown) and found.code is UnknownCode.NO_PARTITION
    on_d0 = load_option_grid(context(store_with(old), D0), AAA)  # D0's own chain is D0's
    assert isinstance(on_d0, OptionGrid) and on_d0.session == D0


def test_no_curve_is_no_partition_never_a_zero_rate() -> None:
    def no_curve(writer: StoreWriter) -> None:
        write_chains(writer, D1, chain_rows(AAA, D1, 100.0, EXPIRIES, R), {AAA: 100.0})

    found = grid(no_curve)
    assert isinstance(found, Unknown) and found.code is UnknownCode.NO_PARTITION


def test_a_curve_stored_after_the_session_is_not_used() -> None:
    def later(writer: StoreWriter) -> None:
        write_chains(writer, D1, chain_rows(AAA, D1, 100.0, EXPIRIES, R), {AAA: 100.0})
        write_curve(writer, D1 + timedelta(days=3), R)

    found = grid(later)
    assert isinstance(found, Unknown) and found.code is UnknownCode.NO_PARTITION


def test_an_underlying_without_chain_rows_is_no_row_and_a_non_optionable_one_not_applicable() -> (
    None
):
    def other(writer: StoreWriter) -> None:
        write_chains(writer, D1, chain_rows("EQ:OTHER", D1, 50.0, EXPIRIES, R), {"EQ:OTHER": 50.0})
        write_curve(writer, D1, R)

    ctx = context(store_with(other))
    none = load_option_grid(ctx, AAA)
    assert isinstance(none, Unknown) and none.code is UnknownCode.NO_ROW
    etf = load_option_grid(ctx, ETF)  # optionable = False in the reference snapshot
    assert isinstance(etf, Unknown) and etf.code is UnknownCode.NOT_APPLICABLE


def test_no_positive_spot_is_not_priced() -> None:
    def no_spot(writer: StoreWriter) -> None:
        write_chains(writer, D1, chain_rows(AAA, D1, 100.0, EXPIRIES, R), {AAA: 0.0})
        write_curve(writer, D1, R)

    found = grid(no_spot)
    assert isinstance(found, Unknown) and found.code is UnknownCode.NO_ROW


def test_a_bucket_without_an_expiry_or_with_a_duplicate_is_a_gap_column() -> None:
    only = {D1 + timedelta(days=35): 0.25}  # near 30 (and 45), in no other window

    def thin(writer: StoreWriter) -> None:
        chain(writer, only)

    g = good(grid(thin))
    by_bucket = {c.bucket: c for c in g.columns}
    assert by_bucket[30].expiry == D1 + timedelta(days=35)
    for bucket in (7, 14, 60, 90):
        gap = by_bucket[bucket].gap
        assert gap is not None and gap.code is UnknownCode.NOT_APPLICABLE
    dup = by_bucket[45].gap  # the 30-day bucket took the one expiry
    assert dup is not None and "took" in dup.cause.links[0].message
    row = g.puts[[c.bucket for c in g.columns].index(7)]
    assert all(isinstance(cell, Unknown) for cell in row)


def test_a_one_sided_chain_is_illiquid() -> None:
    expiry = D1 + timedelta(days=30)

    def one_sided(writer: StoreWriter) -> None:
        rows = [quote_row(AAA, D1, expiry, "P", k, 0.0, 0.5, 1.0, 10.0) for k in (90.0, 95.0)]
        rows += [quote_row(AAA, D1, expiry, "C", k, 1.0, 1.2, 1.0, 10.0) for k in (105.0, 110.0)]
        write_chains(writer, D1, rows, {AAA: 100.0})
        write_curve(writer, D1, R)

    g = good(grid(one_sided))
    puts = g.puts[2]
    assert all(isinstance(c, Unknown) and c.code is UnknownCode.ILLIQUID for c in puts)


def test_no_strike_near_a_band_is_a_gap_not_the_nearest_far_one() -> None:
    def sparse(writer: StoreWriter) -> None:
        rows = chain_rows(
            AAA, D1, 100.0, {D1 + timedelta(days=30): 0.25}, R, strikes=(50, 100, 150)
        )
        write_chains(writer, D1, rows, {AAA: 100.0})
        write_curve(writer, D1, R)

    g = good(grid(sparse))
    cells = g.puts[g.columns.index(next(c for c in g.columns if c.bucket == 30))]
    assert all(isinstance(c, Unknown) and c.code is UnknownCode.NOT_APPLICABLE for c in cells)


def test_the_report_date_decides_report_inside_and_an_unknown_date_is_never_false() -> None:
    def earnings(writer: StoreWriter) -> None:
        chain(writer)
        write_rows(
            writer, "rollups/instrument/earnings@v1", D1,
            [{"instrument_id": AAA, "next_earnings_date": D1 + timedelta(days=20),
              "days_to_earnings": 14}],
        )  # fmt: skip

    g = good(grid(earnings))
    inside = {c.bucket: c.report_inside for c in g.columns}
    assert inside == {7: False, 14: False, 30: True, 45: True, 60: True, 90: True}
    unknown = good(grid(chain))
    assert all(c.report_inside is None for c in unknown.columns)  # never False
    assert all(isinstance(c.report_inside_unknown, Unknown) for c in unknown.columns)


def test_q_is_known_only_when_the_dividend_yield_is_stored() -> None:
    def with_q(writer: StoreWriter) -> None:
        chain(writer)
        write_rows(
            writer,
            "rollups/instrument/div_yield@v1",
            D1,
            [{"instrument_id": AAA, "div_yield": 0.02}],
        )

    assert good(grid(with_q)).q_known is True
    assert good(grid(chain)).q_known is False


def test_the_grid_is_kept_for_the_published_state() -> None:
    reader = store_with(chain)
    ctx = context(reader)
    first = load_option_grid(ctx, AAA)
    assert load_option_grid(ctx, AAA) is first


def test_the_cells_are_deterministic() -> None:
    a, b = good(grid(chain)), good(grid(chain))
    assert a == b
    assert not np.isnan([c.mid for row in a.puts for c in row if isinstance(c, GridCell)]).any()
