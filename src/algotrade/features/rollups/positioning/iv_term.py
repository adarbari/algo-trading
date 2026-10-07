"""``iv_term@v1``: two more points on the at-the-money term structure beside ``iv30@v1``: the
vol at the next expiry and the constant 90-day vol (``docs/data/positioning.md``, ADR 0031).

Inputs: the session's ``chains/option_quotes`` and ``rates/treasury`` (required),
``chains/underlying_quotes`` and ``div_yield@v1`` (optional; a missing yield prices with
``q = 0``). One row per underlying with a chain or an underlying quote. Parameters:
``IvTermParams`` (``rollups.toml ["iv_term@v1"]``: ``iv30@v1``'s keys, with the 90-day
target and its 30..180 day window). Spot is the shared rule (``closing_spots``: the close,
else the price), where ``iv30@v1`` reads the price.

Both vols are ``iv30@v1``'s method (``expiry_vols``: the two strikes around the forward, the
quality filters, call and put vols averaged, linear in strike to the forward):

- ``iv_next``: the ATM vol at the next expiry, the first listed with ``dte >= 1`` (weeklies
  included), no interpolation;
- ``iv_90d``: the expiries ``choose_expiries`` picks around 90 days among ``min_days..max_days``
  (30..180; standard monthlies first), interpolated in total variance to 90 days (``term_vol``).
  It needs both expiries of the pair: one usable expiry is not a 90-day vol, so unlike
  ``iv30@v1``'s SINGLE_EXPIRY it is null.

``iv_term_status``, first failing step wins; a value is kept whenever its own side exists:

    NO_SPOT   no positive underlying close or price
    NO_CHAIN  no option quotes for the underlying
    NO_NEXT   no ``iv_next`` (no expiry 1+ days out, or no ATM vol there; ``iv_90d`` may exist)
    NO_90D    ``iv_next`` exists, no ``iv_90d`` (no bracketing pair 30..180 days out with ATM vols)
    OK        both
"""

from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

from algotrade.features.framework.declaration import FeatureGroup, Input, Inputs, column_types
from algotrade.features.framework.feature import Feature
from algotrade.features.rollups.options.iv30 import (
    DIVIDENDS,
    RATES,
    Iv30Params,
    div_yields,
    expiry_vols,
    pricing_inputs,
    selected_expiries,
    term_vol,
)
from algotrade.features.rollups.positioning.chain_inputs import (
    OPTIONS,
    UNDERLYINGS,
    read_chain,
)
from algotrade.quant.rates import DAYS_PER_YEAR

NAME = "iv_term"
VERSION = 1
STATUSES = ("OK", "NO_SPOT", "NO_CHAIN", "NO_NEXT", "NO_90D")

_QUOTES = tuple(f"{OPTIONS}.{c}" for c in ("bid", "ask", "strike", "expiry", "open_interest"))
_INPUTS = (
    *_QUOTES,
    *(f"{UNDERLYINGS}.{c}" for c in ("close", "price")),
    f"{RATES}.rate_cont",
    "div_yield@v1",
)

FEATURES = (
    Feature(
        "iv_term_status", "str", "category",
        "OK, or the first failing step: NO_SPOT, NO_CHAIN, NO_NEXT (no ATM vol at the next "
        "expiry), NO_90D (no bracketing pair of expiries 30..180 days out with ATM vols); the "
        "side that exists keeps its value",
        "never", "label", categories=STATUSES, inputs=_INPUTS,
    ),
    Feature(
        "iv_next", "float32", "decimal",
        "The at-the-money vol at the next expiry (the first listed with dte >= 1, weeklies "
        "included): iv30's forward ATM method on that one expiry, no interpolation; a very "
        "short expiry is noisy and carries any event in it",
        "iv_term_status is NO_SPOT, NO_CHAIN or NO_NEXT (the status says why)", "chain",
        valid_range=(0, 5), inputs=_INPUTS,
    ),
    Feature(
        "iv_90d", "float32", "decimal",
        "Our constant 90-day at-the-money vol: iv30's method with the two expiries around 90 "
        "days among 30..180 (standard monthlies first), interpolated in total variance",
        "iv_term_status is NO_SPOT, NO_CHAIN or NO_90D, or NO_NEXT with no bracketing pair "
        "(a single usable expiry is not a 90-day vol)", "chain", valid_range=(0, 5),
        inputs=_INPUTS,
    ),
)  # fmt: skip
COLUMNS = column_types(FEATURES)


@dataclass(frozen=True)
class IvTermParams:
    target_days: int = 90  # the constant maturity of iv_90d
    min_days: int = 30  # its expiries are min_days..max_days out
    max_days: int = 180
    max_spread_pct: float = 0.35  # (ask - bid) / mid, as iv30@v1
    min_open_interest: int = 10  # a quote passes with this open interest ...
    min_volume: int = 1  # ... or this volume

    def __post_init__(self) -> None:
        self.vol_rules()  # the same checks as iv30@v1's

    def vol_rules(self) -> Iv30Params:
        """The ``iv30@v1`` parameters ``choose_expiries`` and ``expiry_vols`` read."""
        return Iv30Params(
            target_days=self.target_days,
            min_days=self.min_days,
            max_days=self.max_days,
            max_spread_pct=self.max_spread_pct,
            min_open_interest=self.min_open_interest,
            min_volume=self.min_volume,
        )


def _status(iv_next: float, iv_90d: float, spot: float, has_chain: bool) -> str:
    if np.isnan(spot):
        return "NO_SPOT"
    if not has_chain:
        return "NO_CHAIN"
    if np.isnan(iv_next):
        return "NO_NEXT"
    return "OK" if np.isfinite(iv_90d) else "NO_90D"


def compute(inputs: Inputs, session: date, p: IvTermParams) -> pd.DataFrame:
    curve, spots, options, ids = read_chain(inputs)
    rules = p.vol_rules()
    priced = options[options["underlying_id"].isin(spots.dropna().index)]
    pairs = priced[["underlying_id", "expiry"]].drop_duplicates()
    chosen = selected_expiries(pairs, session, rules)
    ahead = pairs.assign(dte=[(e - session).days for e in pairs["expiry"]])
    ahead = ahead[ahead["dte"] >= 1].sort_values(["underlying_id", "dte"])
    chosen = pd.concat([chosen, ahead.drop_duplicates("underlying_id").assign(role="next")])
    yields = div_yields(inputs.get(DIVIDENDS), session)
    quotes = pricing_inputs(priced, chosen, spots, yields, curve, session)
    vols = chosen.merge(expiry_vols(quotes, rules), on=["underlying_id", "expiry"], how="left")
    ok = vols[vols["status"] == "OK"]
    t_target = p.target_days / DAYS_PER_YEAR
    iv_next = ok[ok["role"] == "next"].set_index("underlying_id")["atm_iv"]
    iv_90d = {}
    for uid, g in ok[ok["role"] != "next"].groupby("underlying_id"):
        by_role = {
            str(role): ((e - session).days / DAYS_PER_YEAR, float(iv))
            for role, e, iv in zip(
                g["role"].tolist(), g["expiry"].tolist(), g["atm_iv"].tolist(), strict=True
            )
        }
        if "near" in by_role and "far" in by_role:  # one usable expiry is not a 90-day vol
            iv_90d[uid] = term_vol(by_role["near"], by_role["far"], t_target)[0]
    out = pd.DataFrame(index=ids)
    out["iv_next"] = iv_next.reindex(ids)
    out["iv_90d"] = pd.Series(iv_90d, dtype=float).reindex(ids)
    with_chain = ids.isin(set(options["underlying_id"]))
    out["iv_term_status"] = [
        _status(n, d, spots.get(i, np.nan), c)
        for i, n, d, c in zip(ids, out["iv_next"], out["iv_90d"], with_chain.tolist(), strict=True)
    ]
    return out.reset_index().reindex(columns=["instrument_id", *COLUMNS])


GROUP = FeatureGroup(
    NAME,
    VERSION,
    "The at-the-money vol at the next expiry and at a constant 90 days (iv30's method), the "
    "two points the term ratios compare with iv30",
    (
        Input(OPTIONS),
        Input(RATES),
        Input(UNDERLYINGS, required=False),
        Input(DIVIDENDS, required=False),
    ),
    FEATURES,
    compute,
    IvTermParams(),
    applies_to="optionable",
)
