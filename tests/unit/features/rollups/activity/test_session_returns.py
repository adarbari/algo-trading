"""``session_returns@v1``: the overnight and intraday compounded returns, by hand; the two
compound to the close-to-close return; a gap, a missing open or a short history is null."""

import numpy as np

from algotrade.features.framework.runner import compute_one
from algotrade.features.registry import GROUPS
from algotrade.features.rollups.activity import session_returns as sr
from tests.helpers.rollup_store import END, store, write_bars


def test_overnight_and_intraday_by_hand() -> None:
    n = 30
    # A name whose whole move happens overnight: it opens 1% above the previous close and
    # closes at its open every day.
    overnight = 100.0 * 1.01 ** np.arange(n)
    writer, reader = store()
    write_bars(
        writer,
        {"EQ:NIGHT": overnight, "EQ:SHORT": overnight[:10]},
        opens={"EQ:NIGHT": overnight},
    )
    frame = compute_one(reader, GROUPS["session_returns@v1"], END).frame
    assert frame is not None
    rows = frame.set_index("instrument_id")
    assert abs(rows.loc["EQ:NIGHT", "overnight_ret_20d"] - (1.01**20 - 1)) < 1e-5
    assert abs(rows.loc["EQ:NIGHT", "intraday_ret_20d"]) < 1e-6
    assert np.isnan(rows.loc["EQ:SHORT", "overnight_ret_20d"])


def test_the_two_parts_compound_to_the_close_to_close_return() -> None:
    rng = np.random.default_rng(3)
    closes = 100.0 * np.exp(np.cumsum(rng.normal(0, 0.01, (sr.WINDOW + 1, 2)), axis=0))
    opens = closes * np.exp(rng.normal(0, 0.005, closes.shape))
    overnight, intraday = sr.session_split(opens, closes)
    total = (1 + overnight) * (1 + intraday) - 1
    assert np.allclose(total, closes[-1] / closes[0] - 1, atol=1e-12)


def test_gaps_and_bad_opens_are_unknown() -> None:
    closes = np.full((sr.WINDOW + 1, 3), 100.0)
    opens = np.full((sr.WINDOW + 1, 3), 100.0)
    closes[7, 0] = np.nan  # a missing close
    opens[7, 1] = np.nan  # a missing open
    opens[9, 2] = 0.0  # a non-positive open is not a price
    overnight, intraday = sr.session_split(opens, closes)
    assert np.isnan(overnight).all() and np.isnan(intraday).all()
    opens[0, 1] = np.nan  # the first row's open is not in the window: it never matters
    opens[7, 1] = 100.0
    assert not np.isnan(sr.session_split(opens, np.full_like(closes, 100.0))[0][1])
