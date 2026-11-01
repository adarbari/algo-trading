"""The one pick of a short option at a band and an expiry bucket: the expiry nearest a target
within its window (ties to the earlier, distinct across buckets), the strike nearest the band
by our delta within the tolerance, and the figures of the sold option; its misses by reason."""

from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from algotrade.features.rollups.premium import band_pick as bp
from algotrade.quant.rates import YieldCurve
from tests.helpers.rollup_store import END, chain_rows, quote_row

CURVE = YieldCurve.from_days(pd.Series([30, 365]), pd.Series([0.03, 0.03]))
E30 = END + timedelta(days=30)


def days(*n: int) -> list[date]:
    return [END + timedelta(days=d) for d in n]


def chain(strikes: tuple[float, ...] = tuple(np.arange(70.0, 130.5, 0.5))) -> pd.DataFrame:
    rows = chain_rows("EQ:A", END, 100.0, {E30: 0.25}, 0.03, strikes=strikes)
    return pd.DataFrame(rows)


def test_the_expiry_is_the_nearest_within_thirty_percent_ties_to_the_earlier() -> None:
    assert bp.pick_expiry(days(25, 34, 50), END, 30) == END + timedelta(days=34)
    assert bp.pick_expiry(days(25, 35), END, 30) == END + timedelta(days=25)  # 5 and 5: earlier
    assert bp.pick_expiry(days(21, 39), END, 30) == END + timedelta(days=21)  # edges count
    assert bp.pick_expiry(days(20, 40), END, 30) is None  # outside 30% of 30 days
    assert bp.pick_expiry([], END, 30) is None
    assert bp.pick_expiry([END], END, 1) is None  # an expiry on the session is no bucket


def test_buckets_never_offer_one_expiry_twice() -> None:
    out = bp.bucket_expiries(days(35), END)
    by_target = {b.target: b for b in out}
    assert by_target[30].expiry == END + timedelta(days=35)
    assert by_target[45].reason == bp.DUPLICATE_EXPIRY and by_target[45].expiry is None
    assert by_target[7].reason == bp.NO_EXPIRY and by_target[90].reason == bp.NO_EXPIRY
    distinct = bp.bucket_expiries(days(7, 14, 30, 45, 60, 90), END)
    assert [b.expiry for b in distinct] == days(7, 14, 30, 45, 60, 90)


def test_the_pick_is_the_strike_nearest_the_band_with_the_figures_of_a_sold_option() -> None:
    deltas = bp.OurDeltas(CURVE, 0.0)
    cell = bp.pick_band(chain(), END, E30, 100.0, 0.20, bp.PUT, deltas)
    assert isinstance(cell, bp.BandCell)
    assert cell.delta == pytest.approx(-0.20, abs=0.01) and cell.iv == pytest.approx(0.25, abs=1e-5)
    assert cell.roc == pytest.approx(cell.mid / cell.strike)
    assert cell.yield_ann == pytest.approx(cell.roc * 365 / 30)
    assert cell.breakeven == pytest.approx(cell.strike - cell.mid)
    assert 0 < cell.p_below < 0.5 and cell.open_interest == 500
    call = bp.pick_band(chain(), END, E30, 100.0, 0.20, bp.CALL, deltas)
    assert isinstance(call, bp.BandCell) and call.delta > 0
    assert call.breakeven == pytest.approx(100.0 - call.mid)


def test_a_band_with_no_strike_within_the_tolerance_is_no_strike() -> None:
    sparse = chain((50.0, 100.0, 150.0))
    found = bp.pick_band(sparse, END, E30, 100.0, 0.20, bp.PUT, bp.OurDeltas(CURVE, 0.0))
    assert found == bp.BandMiss(bp.NO_STRIKE)


def test_a_pool_without_a_two_sided_quote_is_illiquid() -> None:
    rows = pd.DataFrame([quote_row("EQ:A", END, E30, "P", k, 0.0, 0.4, 1.0, 5.0) for k in (90, 95)])
    found = bp.pick_band(rows, END, E30, 100.0, 0.20, bp.PUT, bp.OurDeltas(CURVE, 0.0))
    assert found == bp.BandMiss(bp.ILLIQUID)
    later = E30 + timedelta(days=1)  # no quotes at that expiry
    missing = bp.pick_band(chain(), END, later, 100.0, 0.2, bp.PUT, bp.OurDeltas(CURVE, 0.0))
    assert missing == bp.BandMiss(bp.ILLIQUID)


def test_the_dividend_yield_moves_the_delta_the_way_the_wings_price_it() -> None:
    plain = bp.pick_band(chain(), END, E30, 100.0, 0.20, bp.CALL, bp.OurDeltas(CURVE, 0.0))
    paying = bp.pick_band(chain(), END, E30, 100.0, 0.20, bp.CALL, bp.OurDeltas(CURVE, 0.05))
    assert isinstance(plain, bp.BandCell) and isinstance(paying, bp.BandCell)
    assert paying.iv != plain.iv  # a yield changes the vol a mid implies


def test_one_solve_per_pool_serves_every_band() -> None:
    deltas = bp.OurDeltas(CURVE, 0.0)
    frame = chain()
    for band in bp.BANDS:
        bp.pick_band(frame, END, E30, 100.0, band, bp.PUT, deltas)
    assert len(deltas._solved) == 1
