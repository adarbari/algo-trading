"""``call_wing@v1``: the covered call to sell at the 30-60 day expiry, aiming for 15-30 delta.

The covered-call mirror of ``put_wing@v1`` (the options-strategy audit's call-side gap; plan
``docs/data/technical.md``), run by the same search (``wing_search``: the target expiry, our
delta from the mid through ``quant.implied_vol`` and ``quant.black_scholes``, the band
distance, the band totals, the statuses and the inputs are described there). What differs:

- **Candidates**: its calls whose OUR delta is in ``search_lo..search_hi`` (0.05..0.50).
- **Target band**: ``delta_lo..delta_hi`` (0.15..0.30, the covered-call convention; edges
  included).
- **Best call**: the candidate nearest the band (``delta_band_distance``: 0 inside, else the
  distance to the nearer edge), then the highest ``best_call_yield`` = mid / the underlying's
  price (the premium the covered call collects for the period, per dollar of stock held),
  then the higher open interest, then the higher strike (more room before the shares are
  called away).
- **Band totals**: strikes, open interest and volume of the calls inside the band, and their
  median relative spread.

Our delta is the Black-Scholes-Merton CALL delta at the vol its mid implies, with ``q`` the
dividend yield (``div_yield@v1``): a call before an ex-dividend date is priced as European, so
``cc_*`` features say nothing of early exercise (the ``ex_div_before_expiry`` flag in
``config/site/features/earnings.toml`` does). Spreads are the stored (end-of-day, possibly
after-hours) quote's: judge the trade's spread on a live quote.

One row per underlying with a chain or an underlying quote. ``wing_status``, first failing
step wins:

    NO_SPOT       no positive underlying price
    NO_CHAIN      no call quotes for the underlying
    NO_EXPIRY     no call expiry dte_min..dte_max days out
    NO_STRIKE     no call at the target expiry with our delta in search_lo..search_hi
    OUTSIDE_BAND  a best call, but none in the target band (delta_band_distance > 0)
    OK            the best call is in the target band

Parameters: ``CallWingParams`` (``config/site/rollups.toml ["call_wing@v1"]``). The windows and
bands are named in the feature descriptions and valid ranges: changing them is a new version,
like a window named in a column.
"""

from dataclasses import dataclass
from datetime import date

import pandas as pd

from algotrade.features.framework.declaration import FeatureGroup, Input, Inputs, column_types
from algotrade.features.rollups.options import wing_search
from algotrade.features.rollups.options.iv30 import DIVIDENDS, OPTIONS, RATES, UNDERLYINGS
from algotrade.features.rollups.options.wing_search import WingParams

NAME = "call_wing"
VERSION = 1
SIDE = wing_search.Side(
    right="C", name="call", yield_name="yield", per="spot", lower_strike=False, sign=1,
    yield_rank="premium yield",
    yield_text="premium yield for the period: mid / the underlying's price (the covered "
    "call's income per dollar of stock held)",
)  # fmt: skip


@dataclass(frozen=True, kw_only=True)
class CallWingParams(WingParams):
    delta_lo: float = 0.15  # the target delta band (the covered-call convention)
    delta_hi: float = 0.30
    search_lo: float = 0.05  # candidates: search_lo <= delta <= search_hi
    search_hi: float = 0.50


FEATURES = wing_search.wing_features(SIDE, CallWingParams())
COLUMNS = column_types(FEATURES)


def compute(inputs: Inputs, session: date, p: CallWingParams) -> pd.DataFrame:
    return wing_search.compute(inputs, session, p, SIDE, ["instrument_id", *COLUMNS])


GROUP = FeatureGroup(
    NAME,
    VERSION,
    "The covered call at the expiry nearest 45 days: the one nearest 15-30 delta (our delta), "
    "then by premium yield; band OI, volume and spread",
    (
        Input(OPTIONS),
        Input(RATES),
        Input(UNDERLYINGS, required=False),
        Input(DIVIDENDS, required=False),
    ),
    FEATURES,
    compute,
    CallWingParams(),
    applies_to="optionable",
)
