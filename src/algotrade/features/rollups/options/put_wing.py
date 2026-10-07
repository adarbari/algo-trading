"""``put_wing@v1``: the short put to sell at the 30-60 day expiry, aiming for 8-15 delta.

The VRP scanner's option-trade follow-up (``docs/screeners/vrp-scanner.md``; owner decision
2026-10-04: delta closeness is scored, not gated). Per underlying and session:

- **Target expiry**: the expiry closest to ``dte_target`` (45) calendar days among those
  ``dte_min..dte_max`` (30..60) days out (ties: the earlier), the standard monthlies first when
  ``prefer_monthly`` (open interest concentrates there; a weekly nearer 45 days is usually
  thin), else any listed expiry.
- **Candidates**: its puts whose OUR |delta| is in ``search_lo..search_hi`` (0.05..0.35).
- **Best put**: the candidate closest to the target band ``delta_lo..delta_hi`` (0.08..0.15,
  edges included), i.e. the smallest ``delta_band_distance`` (0 inside the band, else the
  distance to the nearer edge), then the highest cash-secured ROC = premium / (strike x 100)
  per contract = mid / strike, then the higher open interest, then the lower strike. So a
  chain without an 8-15 delta strike still has a best put (say 20 delta, distance 0.05), and a
  screen scores the distance instead of rejecting it.
- **Band totals**: strikes, open interest and volume of the puts inside the band, and their
  median relative spread.

Our delta (ADR 0021; the feed's ``delta`` column is a cross-check only), the statuses and the
inputs are the shared wing search's (``wing_search``; ``call_wing@v1`` is its covered-call
mirror). Spreads are the stored (end-of-day, possibly after-hours) quote's: judge the trade's
spread on a live quote (the best put's strike and expiry identify it).

One row per underlying with a chain or an underlying quote. ``wing_status``, first failing
step wins:

    NO_SPOT       no positive underlying price
    NO_CHAIN      no put quotes for the underlying
    NO_EXPIRY     no put expiry dte_min..dte_max days out
    NO_STRIKE     no put at the target expiry with our |delta| in search_lo..search_hi
    OUTSIDE_BAND  a best put, but none in the target band (delta_band_distance > 0)
    OK            the best put is in the target band

Parameters: ``PutWingParams`` (``config/site/rollups.toml ["put_wing@v1"]``). The windows and
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

NAME = "put_wing"
VERSION = 1
SIDE = wing_search.Side(
    right="P", name="put", yield_name="roc", per="strike", lower_strike=True, sign=-1,
    yield_rank="ROC",
    yield_text="cash-secured return on capital: premium / (strike x 100) = mid / strike",
)  # fmt: skip


@dataclass(frozen=True, kw_only=True)
class PutWingParams(WingParams):
    delta_lo: float = 0.08  # the target |delta| band, both edges included
    delta_hi: float = 0.15
    search_lo: float = 0.05  # candidates: search_lo <= |delta| <= search_hi
    search_hi: float = 0.35


FEATURES = wing_search.wing_features(SIDE, PutWingParams())
COLUMNS = column_types(FEATURES)


def compute(inputs: Inputs, session: date, p: PutWingParams) -> pd.DataFrame:
    return wing_search.compute(inputs, session, p, SIDE, ["instrument_id", *COLUMNS])


GROUP = FeatureGroup(
    NAME,
    VERSION,
    "The short put at the expiry nearest 45 days: the one nearest 8-15 delta (our delta), "
    "then by cash-secured ROC; band OI, volume and spread",
    (
        Input(OPTIONS),
        Input(RATES),
        Input(UNDERLYINGS, required=False),
        Input(DIVIDENDS, required=False),
    ),
    FEATURES,
    compute,
    PutWingParams(),
    applies_to="optionable",
)
