"""``market_bear_probit@v1``: the bear-state probit, one ``MKT:US`` row per session (ADR 0047;
docs/market-regime-plan.md section 3E: Chen 2009, Nyberg 2013).

    bear_prob_6m      ncdf(b0 + b_curve * curve_10y3m + b_cpi * cpi_yoy + b_hy * hy_oas): the
                      probability that the S&P 500 is in a bear market six months on, from the
                      session's ``market_macro@v2`` columns (decimals) and ``quant.probit``
    bear_prob_source  where the coefficients come from: ``fitted`` (the episode scorecard's fit
                      on our stored history, pasted into ``config/site/rollups.toml``) or
                      ``literature`` (the defaults below: the signs Chen 2009 found, a falling
                      term spread and rising inflation and credit spreads raise the risk, with
                      magnitudes of that order, not fitted on our data)

The coefficients are typed site params (``rollups.toml ["market_bear_probit@v1"]``, with
``fitted``). It is shown beside ``regime.macro_risk`` as a second opinion; it never sets the
label. Both columns are null when an input is (the high-yield spread starts in 1997).

Licence: personal (ADR 0028, via ADR 0047): the probability is a direct function of the ICE
BofA high-yield spread, a personal-use value.
"""

import math
from dataclasses import dataclass, fields
from datetime import date

import numpy as np
import pandas as pd

from algotrade.core.model.instruments import market_id
from algotrade.features.framework.declaration import FeatureGroup, Input, Inputs, column_types
from algotrade.features.framework.feature import Feature
from algotrade.features.rollups.market import macro
from algotrade.features.rollups.market.indicators import number, session_values
from algotrade.quant.probit import predict

NAME = "market_bear_probit"
VERSION = 1
REGRESSORS = ("curve_10y3m", "cpi_yoy", "hy_oas")  # market_macro columns, in coefficient order
SOURCES = ("fitted", "literature")
HORIZON_SESSIONS = 126  # six months: the bear state the probability is about


@dataclass(frozen=True)
class Params:
    """The probit's coefficients on decimal inputs (``fitted``: estimated on our history by the
    episode scorecard, else literature-order values)."""

    b0: float = -1.0
    b_curve: float = -40.0  # 1 point of 10y - 3m less (0.01): z down 0.4
    b_cpi: float = 15.0  # 1 point more CPI inflation: z up 0.15
    b_hy: float = 10.0  # 1 point wider high-yield spread: z up 0.1
    fitted: bool = False

    def __post_init__(self) -> None:
        if not all(math.isfinite(getattr(self, f.name)) for f in fields(self)[:4]):
            raise ValueError("the probit coefficients must be finite")

    @property
    def coef(self) -> np.ndarray:
        return np.array([self.b0, self.b_curve, self.b_cpi, self.b_hy])


D = Params()
_READS = tuple(macro.GROUP.feature(c).key for c in REGRESSORS)
_NULL = "curve_10y3m, cpi_yoy or hy_oas is null for the session (hy_oas starts in 1997)"

FEATURES = (
    Feature("bear_prob_6m", "float32", "decimal", f"Bear-state probit: the probability that the "
            f"S&P 500 is in a bear market {HORIZON_SESSIONS} sessions on, ncdf(b0 + b_curve x "
            "curve_10y3m + b_cpi x cpi_yoy + b_hy x hy_oas) with the site's coefficients "
            f"(defaults {D.b0:g}, {D.b_curve:g}, {D.b_cpi:g}, {D.b_hy:g}: literature-order, "
            "not fitted)", _NULL, valid_range=(0, 1), inputs=_READS, licence="personal"),
    Feature("bear_prob_source", "str", "category", "Where bear_prob_6m's coefficients come "
            "from: fitted (the episode scorecard's fit on stored history) or literature "
            "(literature-order defaults)", _NULL, kind="label", categories=SOURCES,
            inputs=_READS),
)  # fmt: skip
COLUMNS = column_types(FEATURES)


def bear_probability(values: dict[str, object], params: Params) -> float:
    """``bear_prob_6m`` from one session's ``market_macro`` columns (NaN: an input is null)."""
    x = np.array([1.0, *(number(values, c) for c in REGRESSORS)])
    return float(predict(x, params.coef))


def compute(inputs: Inputs, session: date, params: Params) -> pd.DataFrame:
    prob = bear_probability(session_values(inputs, session), params)
    known = not np.isnan(prob)
    row = {
        "instrument_id": market_id("US"),
        "bear_prob_6m": prob,
        "bear_prob_source": ("fitted" if params.fitted else "literature") if known else None,
    }
    return pd.DataFrame([row], columns=["instrument_id", *COLUMNS])


GROUP = FeatureGroup(
    NAME,
    VERSION,
    "The bear-state probit (Chen 2009, Nyberg 2013): the probability of a bear market six "
    "months on from the term spread, inflation and the high-yield spread, a second opinion "
    "beside the regime's macro risk",
    (Input(macro.GROUP.table, required=False),),
    FEATURES,
    compute,
    params=D,
    entity="market",
)
