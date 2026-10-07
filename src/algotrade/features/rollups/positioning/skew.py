"""``skew@v1``: the 25-delta risk reversal over the at-the-money vol at a constant 30 days
(``docs/data/positioning.md`` OP3, ADR 0031).

Inputs: the session's ``chains/option_quotes`` and ``rates/treasury`` (required),
``chains/underlying_quotes`` and ``div_yield@v1`` (optional; a missing yield prices with
``q = 0``). One row per underlying with a chain or an underlying quote. Parameters:
``SkewParams`` (``rollups.toml ["skew@v1"]``). Spot is the shared rule (``closing_spots``).

Per expiry (``t = dte / 365``), over the **smile quotes** only (two-sided, ``(ask - bid) /
mid <= max_spread_pct``): each contract's mid is inverted to its own IV and priced with our
BSM delta at that IV (spot delta, with ``e^{-qt}``; ``wing_search.our_deltas``). Then, linear
in delta between the two contracts bracketing the target, with no extrapolation (a target
outside the quoted deltas is no value):

- ``iv_25p``: the put IV at delta -0.25;
- ``iv_25c``: the call IV at delta +0.25;
- ``iv_atm``: the mean of the call IV at +0.50 and the put IV at -0.50 (both are needed).

Maturity: the two expiries ``iv30@v1`` chooses (``choose_expiries``: standard monthlies first,
7..90 days out, bracketing 30), each of the three vols interpolated linearly in total variance
``sigma^2 t`` to 30 days (``term_vol``), then ``skew = (iv_25p - iv_25c) / iv_atm`` from the
interpolated vols. An expiry is **usable** when it has all three vols; one usable expiry gives
its vols unchanged (``SINGLE_EXPIRY``). ``ne_skew`` is the same per-expiry formula at the next
expiry (the first listed with ``dte >= 1``, weeklies included), no interpolation; ``ne_dte`` is
its days out.

``skew_status``, first failing step wins:

    NO_SPOT        no positive underlying close or price
    NO_CHAIN       no option quotes for the underlying
    NO_EXPIRY      no expiry 7..90 days out
    NO_ATM         no selected expiry has an ATM vol
    NO_WING        an ATM vol, but no selected expiry brackets both 25-delta targets
    OK             two usable expiries (or one exactly on 30 days)
    SINGLE_EXPIRY  one usable expiry
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
    selected_expiries,
    term_vol,
)
from algotrade.features.rollups.options.wing_search import our_deltas
from algotrade.features.rollups.positioning.chain_inputs import (
    OPTIONS,
    UNDERLYINGS,
    read_chain,
    relative_spread,
    two_sided_mid,
)
from algotrade.quant.rates import DAYS_PER_YEAR, YieldCurve

NAME = "skew"
VERSION = 1
STATUSES = ("OK", "SINGLE_EXPIRY", "NO_SPOT", "NO_CHAIN", "NO_EXPIRY", "NO_ATM", "NO_WING")
WING_DELTA = 0.25  # the risk reversal's wings: |delta| 0.25
ATM_DELTA = 0.50  # the at-the-money vol: the call at +0.50 and the put at -0.50

_QUOTE = tuple(f"{OPTIONS}.{c}" for c in ("bid", "ask", "strike", "expiry", "right"))
_SPOT = (f"{UNDERLYINGS}.close", f"{UNDERLYINGS}.price")
_INPUTS = (*_QUOTE, *_SPOT, f"{RATES}.rate_cont", "div_yield@v1")
_NOT_OK = "skew_status is neither OK nor SINGLE_EXPIRY (the status says why)"
_NO_NEXT = (
    "no chain or spot, no expiry with dte >= 1, or the next expiry has no ATM vol or no "
    "bracketing 25-delta put and call among its smile quotes"
)

FEATURES = (
    Feature(
        "skew_status", "str", "category",
        "OK, SINGLE_EXPIRY (one usable expiry, its vols unchanged), or the first failing step: "
        "NO_SPOT, NO_CHAIN, NO_EXPIRY (none 7..90 days out), NO_ATM (no ATM vol), NO_WING "
        "(25 delta not bracketed on a side)",
        "never", "label", categories=STATUSES, inputs=_INPUTS,
    ),
    Feature(
        "skew", "float32", "ratio",
        "Normalised 25-delta skew at 30 days: (iv_25p - iv_25c) / iv_atm; positive: puts "
        "richer than calls, 0.2 is a put vol 20% of ATM above the call vol",
        _NOT_OK, "chain", valid_range=(-1, 2), inputs=_INPUTS,
    ),
    Feature(
        "iv_25p", "float32", "decimal",
        "The put vol at our delta -0.25 (linear in delta between the two smile quotes "
        "bracketing it), interpolated in total variance to 30 days",
        _NOT_OK, "chain", valid_range=(0, 5), inputs=_INPUTS,
    ),
    Feature(
        "iv_25c", "float32", "decimal",
        "The call vol at our delta +0.25 (linear in delta between the two smile quotes "
        "bracketing it), interpolated in total variance to 30 days",
        _NOT_OK, "chain", valid_range=(0, 5), inputs=_INPUTS,
    ),
    Feature(
        "iv_atm", "float32", "decimal",
        "The at-the-money vol: the mean of the call vol at delta +0.50 and the put vol at "
        "-0.50, interpolated in total variance to 30 days",
        _NOT_OK, "chain", valid_range=(0, 5), inputs=_INPUTS,
    ),
    Feature(
        "ne_skew", "float32", "ratio",
        "The same skew at the next expiry (the first listed with dte >= 1, weeklies included), "
        "no interpolation; very short expiries have noisy vols, read ne_dte",
        _NO_NEXT, "chain", valid_range=(-1, 2), inputs=_INPUTS,
    ),
    Feature(
        "ne_dte", "int", "days",
        "Calendar days from the session to the next expiry (the first listed with dte >= 1)",
        "no option chain, or no listed expiry with dte >= 1", "chain", valid_range=(1, None),
        inputs=(f"{OPTIONS}.expiry",),
    ),
)  # fmt: skip
COLUMNS = column_types(FEATURES)
_VOLS = ("iv_25p", "iv_25c", "iv_atm")


@dataclass(frozen=True)
class SkewParams:
    target_days: int = 30  # the constant maturity of skew, iv_25p, iv_25c and iv_atm
    min_days: int = 7  # the term expiries are min_days..max_days out (as iv30@v1)
    max_days: int = 90
    max_spread_pct: float = 0.35  # a smile quote's (ask - bid) / mid, as iv30@v1

    def __post_init__(self) -> None:
        self.expiry_rules()  # the same checks as iv30@v1's

    def expiry_rules(self) -> Iv30Params:
        """The ``iv30@v1`` parameters ``choose_expiries`` reads."""
        return Iv30Params(
            target_days=self.target_days,
            min_days=self.min_days,
            max_days=self.max_days,
            max_spread_pct=self.max_spread_pct,
        )


def vol_at_delta(delta: np.ndarray, iv: np.ndarray, target: float) -> float:
    """The IV at ``target`` delta, linear between the two contracts bracketing it (the nearest
    at or below and at or above); NaN when no contract is on one side (no extrapolation).
    ``delta`` ascending, ``iv`` aligned."""
    below = int(np.searchsorted(delta, target, side="right")) - 1
    above = int(np.searchsorted(delta, target, side="left"))
    if below < 0 or above >= len(delta):
        return float("nan")
    gap = delta[above] - delta[below]
    if gap <= 0:
        return float(iv[below])  # a contract exactly on the target
    return float(iv[below] + (iv[above] - iv[below]) * (target - delta[below]) / gap)


def _side_vols(priced: pd.DataFrame, targets: dict[str, float]) -> pd.DataFrame:
    """``targets`` (column -> delta) read off each (underlying, expiry) smile of ``priced``
    (rows with ``delta`` and ``iv``): one column per target, indexed by the pair."""
    frame = priced.dropna(subset=["delta"]).sort_values(
        ["underlying_id", "expiry", "delta"], kind="stable"
    )
    rows = {}
    for key, g in frame.groupby(["underlying_id", "expiry"], sort=False):
        delta, iv = g["delta"].to_numpy(dtype=float), g["iv"].to_numpy(dtype=float)
        rows[key] = [vol_at_delta(delta, iv, target) for target in targets.values()]
    index = pd.MultiIndex.from_tuples(rows, names=["underlying_id", "expiry"])
    return pd.DataFrame(list(rows.values()), index=index, columns=list(targets), dtype=float)


def smile_vols(contracts: pd.DataFrame, curve: YieldCurve, p: SkewParams) -> pd.DataFrame:
    """``iv_25p``, ``iv_25c`` and ``iv_atm`` per (``underlying_id``, ``expiry``).

    ``contracts``: ``underlying_id``, ``expiry``, ``dte``, ``right``, ``strike``, ``bid``,
    ``ask``, ``spot``, ``q``. Only smile quotes count; a pair with none is absent."""
    mid = two_sided_mid(contracts["bid"], contracts["ask"])
    smile = contracts[relative_spread(contracts["bid"], contracts["ask"], mid) <= p.max_spread_pct]
    calls = our_deltas(smile[smile["right"] == "C"], curve, True)
    puts = our_deltas(smile[smile["right"] == "P"], curve, False)
    c = _side_vols(calls, {"iv_25c": WING_DELTA, "atm_c": ATM_DELTA})
    q = _side_vols(puts, {"iv_25p": -WING_DELTA, "atm_p": -ATM_DELTA})
    both = c.join(q, how="outer")
    both["iv_atm"] = (both["atm_c"] + both["atm_p"]) / 2  # NaN unless both sides bracket
    return both[list(_VOLS)]


def expiry_skew(vols: dict[str, float] | None) -> float:
    """The skew of one expiry's vols, NaN unless all three exist."""
    if vols is None or not all(np.isfinite(vols[v]) for v in _VOLS):
        return float("nan")
    return (vols["iv_25p"] - vols["iv_25c"]) / vols["iv_atm"]


def term_columns(
    picked: pd.DataFrame | None,
    table: dict[tuple[str, date], dict[str, float]],
    session: date,
    p: SkewParams,
) -> dict[str, object]:
    """The 30-day columns for one underlying from its selected expiries (``picked``: its
    ``underlying_id``, ``expiry`` and ``role`` rows, ``None`` without one) and the per-expiry
    ``table`` of vols."""
    if picked is None:
        return {"skew_status": "NO_EXPIRY"}
    expiries: list[date] = picked["expiry"].tolist()
    found = {
        str(role): (table.get((str(uid), e)), e)
        for uid, e, role in zip(
            picked["underlying_id"].tolist(), expiries, picked["role"].tolist(), strict=True
        )
    }
    usable = {r: (v, e) for r, (v, e) in found.items() if np.isfinite(expiry_skew(v))}
    if not usable:
        has_atm = any(v is not None and np.isfinite(v["iv_atm"]) for v, _ in found.values())
        return {"skew_status": "NO_WING" if has_atm else "NO_ATM"}
    t_target = p.target_days / DAYS_PER_YEAR
    out: dict[str, float] = {}
    status = "OK"
    for name in _VOLS:
        points = {
            r: ((e - session).days / DAYS_PER_YEAR, v[name]) for r, (v, e) in usable.items() if v
        }
        out[name], status = term_vol(points.get("near"), points.get("far"), t_target)
    skew = (out["iv_25p"] - out["iv_25c"]) / out["iv_atm"]
    return {**out, "skew": skew, "skew_status": status if np.isfinite(skew) else "NO_WING"}


def compute(inputs: Inputs, session: date, p: SkewParams) -> pd.DataFrame:
    curve, spots, options, ids = read_chain(inputs)
    priced = options[options["underlying_id"].isin(spots.dropna().index)]
    pairs = priced[["underlying_id", "expiry"]].drop_duplicates()
    chosen = selected_expiries(pairs, session, p.expiry_rules())
    ahead = pairs.assign(dte=[(e - session).days for e in pairs["expiry"]])
    ahead = ahead[ahead["dte"] >= 1].sort_values(["underlying_id", "dte"])
    next_exp = ahead.drop_duplicates("underlying_id").assign(role="next")
    listed = options[["underlying_id", "expiry"]].drop_duplicates()
    listed = listed.assign(dte=[(e - session).days for e in listed["expiry"]])
    next_dte = listed[listed["dte"] >= 1].groupby("underlying_id")["dte"].min()
    need = pd.concat([chosen, next_exp[["underlying_id", "expiry", "role"]]])
    contracts = priced.merge(need[["underlying_id", "expiry"]].drop_duplicates())
    q = div_yields(inputs.get(DIVIDENDS), session)
    contracts = contracts.assign(
        dte=[(e - session).days for e in contracts["expiry"]],
        spot=spots.reindex(contracts["underlying_id"]).to_numpy(dtype=float),
        q=q.reindex(contracts["underlying_id"]).fillna(0.0).to_numpy(dtype=float),
    )
    vols = smile_vols(contracts, curve, p) if len(contracts) else pd.DataFrame(columns=list(_VOLS))
    table = {
        (str(r["underlying_id"]), r["expiry"]): {c: float(r[c]) for c in _VOLS}
        for r in vols.reset_index().to_dict("records")
    }
    terms = dict(tuple(chosen.groupby("underlying_id"))) if len(chosen) else {}
    nexts = next_exp.set_index("underlying_id")["expiry"]
    with_chain = set(options["underlying_id"])
    rows = []
    for iid in ids:
        if np.isnan(spots.get(iid, np.nan)):
            row: dict[str, object] = {"skew_status": "NO_SPOT"}
        elif iid not in with_chain:
            row = {"skew_status": "NO_CHAIN"}
        else:
            row = term_columns(terms.get(iid), table, session, p)
            if iid in nexts.index:
                row["ne_skew"] = expiry_skew(table.get((iid, nexts[iid])))
        if iid in next_dte.index:
            row["ne_dte"] = int(next_dte[iid])
        rows.append({"instrument_id": iid, **row})
    return pd.DataFrame(rows).reindex(columns=["instrument_id", *COLUMNS])


GROUP = FeatureGroup(
    NAME,
    VERSION,
    "The 25-delta skew at 30 days: (put vol - call vol) / ATM vol from our own delta at each "
    "contract's IV, with the three vols and the same skew at the next expiry",
    (
        Input(OPTIONS),
        Input(RATES),
        Input(UNDERLYINGS, required=False),
        Input(DIVIDENDS, required=False),
    ),
    FEATURES,
    compute,
    SkewParams(),
    applies_to="optionable",
)
