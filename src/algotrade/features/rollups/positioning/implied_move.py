"""``implied_move@v1``: the move the options market prices to one expiry, from the at-the-money
straddle (``docs/data/positioning.md`` OP4, ADR 0031).

Inputs: the session's ``chains/option_quotes`` (required), ``chains/underlying_quotes`` and
``earnings@v1`` for the session (both optional). One row per underlying with a chain or an
underlying quote. Parameters: ``ImpliedMoveParams`` (``rollups.toml ["implied_move@v1"]``).

**Spot** ``S0``: the underlying quote's ``close`` when positive, else its ``price``
(``chain_inputs.closing_spots``), because option quotes are closing quotes.

**Expiry** (calendar days ``dte = expiry - session``, listed expiries with ``dte >= 1``):
if ``earnings@v1`` knows the next report and an expiry covers it within ``max_dte``, the first
such expiry (``move_basis = EARNINGS``). An expiry covers a report on date D when it is after
D, or on D when the report is ``pre`` (before the open); ``post`` and ``unknown`` need an
expiry after D. A report whose date is the session and time ``pre`` is already in the
session's close, so it is not ahead: the term expiry is used. Otherwise the listed expiry
nearest ``target_dte`` among ``MIN_TERM_DTE..max_dte`` days out (ties: the earlier;
``move_basis = TERM``).

**Straddle**: at that expiry, the call plus put mid at the two listed strikes around ``S0``
(the highest at or below it and the lowest above it). A strike is usable when both legs are
two-sided (``bid > 0``, ``ask > bid``) with ``(ask - bid) / mid <= max_spread_pct``. Two
usable strikes: the straddle interpolated linearly in strike to ``S0``; one: its straddle.
``implied_move = straddle / S0``: no 0.85 factor (the straddle already prices the expected
absolute move); the one-standard-deviation move is an expression feature.

``move_status``, first failing step wins:

    NO_SPOT       no positive underlying close or price
    NO_CHAIN      no option quotes for the underlying
    NO_EXPIRY     no expiry for either basis (none 1+ days out covering the report within
                  max_dte, none MIN_TERM_DTE..max_dte days out)
    NO_QUOTES     no strike around S0 with both legs two-sided
    WIDE_SPREADS  two-sided legs, but every such strike has a leg wider than max_spread_pct
    OK            a usable strike

The chosen expiry (``move_expiry``, ``move_dte``, ``move_basis``) is reported whenever one was
selected, whatever the quotes then say.
"""

from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

from algotrade.features.framework.declaration import FeatureGroup, Input, Inputs, column_types
from algotrade.features.framework.feature import Feature
from algotrade.features.rollups.positioning.chain_inputs import (
    OPTIONS,
    UNDERLYINGS,
    closing_spots,
    days_to,
    expiry_days,
    relative_spread,
    two_sided_mid,
)

NAME = "implied_move"
VERSION = 1
EARNINGS = "rollups/instrument/earnings@v1"
STATUSES = ("OK", "NO_SPOT", "NO_CHAIN", "NO_EXPIRY", "NO_QUOTES", "WIDE_SPREADS")
BASES = ("EARNINGS", "TERM")
MIN_TERM_DTE = 7  # a term expiry is at least this many days out (pin risk, noisy mids)

_QUOTE = tuple(f"{OPTIONS}.{c}" for c in ("bid", "ask", "strike", "expiry", "right"))
_SPOT = (f"{UNDERLYINGS}.close", f"{UNDERLYINGS}.price")
_REPORT = ("earnings.next_earnings_date@v1", "earnings.earnings_time@v1")
_INPUTS = (*_QUOTE, *_SPOT, *_REPORT)
_NO_EXPIRY = "no expiry was selected (NO_SPOT, NO_CHAIN or NO_EXPIRY)"
_NOT_OK = "move_status is not OK (the status says why)"

FEATURES = (
    Feature(
        "move_status", "str", "category",
        "OK, or the first failing step: NO_SPOT, NO_CHAIN (no quotes), NO_EXPIRY (no expiry "
        "to read), NO_QUOTES (no strike around the spot with both legs two-sided), "
        "WIDE_SPREADS (two-sided but every straddle leg is wider than 35% of mid)",
        "never", "label", categories=STATUSES, inputs=_INPUTS,
    ),
    Feature(
        "implied_move", "float32", "decimal",
        "The expected absolute move to the move expiry priced by the at-the-money straddle: "
        "straddle_mid / spot (0.06 is 6%; no 0.85 factor; spot is the underlying's close)",
        _NOT_OK, "chain", valid_range=(0, 2), inputs=_INPUTS,
    ),
    Feature(
        "straddle_mid", "float32", "usd_per_share",
        "The call + put mid at the spot, interpolated in strike between the two listed "
        "strikes around it (one usable strike: its straddle), per share",
        _NOT_OK, "chain", valid_range=(0, None), inputs=_INPUTS,
    ),
    Feature(
        "move_expiry", "date", "date",
        "The expiry the straddle is read at: the first one covering the next earnings report "
        "within 60 days (EARNINGS), else the one nearest 30 days among 7..60 (TERM)",
        _NO_EXPIRY, "chain", inputs=(f"{OPTIONS}.expiry", *_REPORT),
    ),
    Feature(
        "move_dte", "int", "days", "Calendar days from the session to the move expiry",
        _NO_EXPIRY, "chain", valid_range=(1, None), inputs=(f"{OPTIONS}.expiry", *_REPORT),
    ),
    Feature(
        "move_basis", "str", "category",
        "EARNINGS when the move expiry is the first covering the next report, TERM when it is "
        "the expiry nearest 30 days (no report ahead, or none covered within 60 days)",
        _NO_EXPIRY, "label", categories=BASES, inputs=(f"{OPTIONS}.expiry", *_REPORT),
    ),
)  # fmt: skip
COLUMNS = column_types(FEATURES)


@dataclass(frozen=True)
class ImpliedMoveParams:
    max_dte: int = 60  # the furthest expiry read, in calendar days
    target_dte: int = 30  # the term expiry: the listed one nearest this many days out
    max_spread_pct: float = 0.35  # (ask - bid) / mid of a straddle leg

    def __post_init__(self) -> None:
        if not MIN_TERM_DTE <= self.target_dte <= self.max_dte:
            raise ValueError(f"need {MIN_TERM_DTE} <= target_dte <= max_dte")
        if self.max_spread_pct <= 0:
            raise ValueError("max_spread_pct must be > 0")


def _reports(rows: pd.DataFrame | None, session: date) -> pd.DataFrame:
    """``report`` (``datetime64[D]``, NaT when none) and ``pre`` (before the open) by
    instrument id, from the session's ``earnings@v1`` rows."""
    if rows is None or rows.empty:
        return pd.DataFrame(
            {
                "report": pd.Series([], dtype="datetime64[ns]"),
                "pre": pd.Series([], dtype=bool),
            },
            index=pd.Index([], dtype=str),
        )
    today = rows[rows["session_date"] == session]
    day = pd.to_datetime(today["next_earnings_date"]).to_numpy(dtype="datetime64[D]")
    out = pd.DataFrame(
        {"report": day, "pre": (today["earnings_time"] == "pre").to_numpy()},
        index=today["instrument_id"].astype(str).to_numpy(),
    )
    return out[~out.index.duplicated(keep="last")]


def choose_expiries(
    listed: pd.DataFrame, reports: pd.DataFrame, session: date, p: ImpliedMoveParams
) -> pd.DataFrame:
    """The move expiry per underlying: ``underlying_id``, ``expiry`` (``datetime64[D]``),
    ``dte``, ``basis``. ``listed``: ``underlying_id``, ``expiry``, ``dte`` of every listed
    expiry 1 or more days out. Underlyings with no expiry to read are absent."""
    today = np.datetime64(session, "D")
    window = listed[listed["dte"] <= p.max_dte]
    by_id = window["underlying_id"]
    report = reports["report"].reindex(by_id).to_numpy(dtype="datetime64[D]")
    pre = reports["pre"].reindex(by_id).fillna(False).to_numpy(dtype=bool)
    expiry = window["expiry"].to_numpy(dtype="datetime64[D]")
    ahead = (report > today) | ((report == today) & ~pre)  # NaT compares False
    covers = ahead & ((expiry > report) | ((expiry == report) & pre))
    earnings = window[covers].sort_values(["underlying_id", "expiry"])
    term = window[window["dte"] >= MIN_TERM_DTE]
    term = term.assign(off=(term["dte"] - p.target_dte).abs())
    term = term.sort_values(["underlying_id", "off", "expiry"])
    both = pd.concat([earnings.assign(basis="EARNINGS"), term.assign(basis="TERM")])
    chosen = both.drop_duplicates("underlying_id", keep="first")
    return pd.DataFrame(chosen[["underlying_id", "expiry", "dte", "basis"]])


def _legs(quotes: pd.DataFrame, right: str, p: ImpliedMoveParams) -> pd.DataFrame:
    """One right's quotes by (underlying, strike): ``mid`` (NaN unless two-sided) and
    ``tight`` (two-sided with a spread within ``max_spread_pct``)."""
    side = quotes[quotes["right"] == right].reset_index(drop=True)
    mid = two_sided_mid(side["bid"], side["ask"])
    spread = relative_spread(side["bid"], side["ask"], mid)
    legs = pd.DataFrame(
        {
            "underlying_id": side["underlying_id"],
            "strike": side["strike"].to_numpy(dtype=float),
            "mid": mid,
            "tight": spread <= p.max_spread_pct,
        }
    )
    return legs.drop_duplicates(["underlying_id", "strike"], keep="last")


def straddles(quotes: pd.DataFrame, spots: pd.Series, p: ImpliedMoveParams) -> pd.DataFrame:
    """``straddle_mid`` and ``status`` (OK, NO_QUOTES, WIDE_SPREADS) by ``underlying_id``.

    ``quotes``: the contracts at each underlying's move expiry (``underlying_id``, ``right``,
    ``strike``, ``bid``, ``ask``; string columns, a default index); ``spots``: ``S0`` by
    underlying id. The two strikes are the highest listed at or below ``S0`` and the lowest
    above it; with none on one side (``S0`` outside the listed strikes) there is no pair
    around ``S0`` and no usable strike."""
    spot = spots.reindex(quotes["underlying_id"]).to_numpy(dtype=float)
    strikes = quotes.assign(spot=spot)
    ids = pd.Index(sorted(set(strikes["underlying_id"].unique())))
    k_lo = strikes[strikes["strike"] <= strikes["spot"]].groupby("underlying_id")["strike"].max()
    k_hi = strikes[strikes["strike"] > strikes["spot"]].groupby("underlying_id")["strike"].min()
    around = pd.DataFrame({"k_lo": k_lo, "k_hi": k_hi}).reindex(ids)
    around["spot"] = spots.reindex(ids).to_numpy(dtype=float)
    paired = around["k_lo"].notna() & (around["k_hi"].notna() | (around["k_lo"] == around["spot"]))
    around = around[paired]
    calls, puts = _legs(quotes, "C", p), _legs(quotes, "P", p)
    both = calls.merge(puts, on=["underlying_id", "strike"], suffixes=("_c", "_p"))
    both = both.join(around, on="underlying_id", how="inner")
    both = both[(both["strike"] == both["k_lo"]) | (both["strike"] == both["k_hi"])]
    both = both.assign(
        straddle=both["mid_c"] + both["mid_p"],
        two_sided=both["mid_c"].notna() & both["mid_p"].notna(),
        usable=both["tight_c"] & both["tight_p"],
        low=both["strike"] == both["k_lo"],
    )
    usable = both[both["usable"]]
    s_lo = usable[usable["low"]].set_index("underlying_id")["straddle"]
    s_hi = usable[~usable["low"]].set_index("underlying_id")["straddle"]
    out = pd.DataFrame({"s_lo": s_lo, "s_hi": s_hi}).reindex(ids).join(around)
    weight = (out["spot"] - out["k_lo"]) / (out["k_hi"] - out["k_lo"])
    both_ok = out["s_lo"].notna() & out["s_hi"].notna()
    out["straddle_mid"] = np.where(
        both_ok, out["s_lo"] + (out["s_hi"] - out["s_lo"]) * weight, out["s_lo"].fillna(out["s_hi"])
    )
    flags = both.groupby("underlying_id")[["two_sided", "usable"]].any().reindex(ids)
    out["status"] = np.select(
        [out["straddle_mid"].notna(), flags["two_sided"].fillna(False).astype(bool)],
        ["OK", "WIDE_SPREADS"],
        "NO_QUOTES",
    )
    return out[["straddle_mid", "status"]]


def compute(inputs: Inputs, session: date, p: ImpliedMoveParams) -> pd.DataFrame:
    options = inputs[OPTIONS]
    assert options is not None  # required input
    underlyings = inputs.get(UNDERLYINGS)
    spots = closing_spots(underlyings)
    quoted = set() if underlyings is None else set(underlyings["instrument_id"].astype(str))
    chain = pd.DataFrame(
        {
            "underlying_id": options["underlying_id"].astype(str).reset_index(drop=True),
            "expiry": expiry_days(options["expiry"]),
            "right": options["right"].astype(str).reset_index(drop=True),
            "strike": options["strike"].to_numpy(dtype=float),
            "bid": options["bid"].to_numpy(),
            "ask": options["ask"].to_numpy(),
        }
    )
    chain["dte"] = days_to(chain["expiry"].to_numpy(), session)
    ids = pd.Index(sorted(quoted | set(chain["underlying_id"].unique())), name="instrument_id")
    priced = chain[chain["underlying_id"].isin(spots.dropna().index)]
    listed = priced[priced["dte"] >= 1].drop_duplicates(["underlying_id", "expiry"])
    chosen = choose_expiries(listed, _reports(inputs.get(EARNINGS), session), session, p)
    at_expiry = priced.merge(chosen[["underlying_id", "expiry"]], on=["underlying_id", "expiry"])
    found = straddles(at_expiry, spots, p) if len(at_expiry) else pd.DataFrame()
    chosen = chosen.set_index("underlying_id")
    out = pd.DataFrame(index=ids)
    out["move_expiry"] = pd.to_datetime(chosen["expiry"]).dt.date.reindex(ids)
    out["move_dte"] = chosen["dte"].reindex(ids)
    out["move_basis"] = chosen["basis"].reindex(ids)
    out["straddle_mid"] = found.get("straddle_mid", pd.Series(dtype=float)).reindex(ids)
    out["implied_move"] = out["straddle_mid"] / spots.reindex(ids)
    quote_status = found.get("status", pd.Series(dtype=object)).reindex(ids)
    status = quote_status.fillna("NO_QUOTES").to_numpy(dtype=object)
    status = np.where(out["move_expiry"].isna().to_numpy(), "NO_EXPIRY", status)
    status = np.where(ids.isin(set(chain["underlying_id"].unique())), status, "NO_CHAIN")
    out["move_status"] = np.where(spots.reindex(ids).isna().to_numpy(), "NO_SPOT", status)
    return out.reset_index().reindex(columns=["instrument_id", *COLUMNS])


GROUP = FeatureGroup(
    NAME,
    VERSION,
    "The move priced by the at-the-money straddle at the expiry covering the next earnings "
    "report (else the term expiry nearest 30 days), as a share of the spot",
    (
        Input(OPTIONS),
        Input(UNDERLYINGS, required=False),
        Input(EARNINGS, required=False),
    ),
    FEATURES,
    compute,
    ImpliedMoveParams(),
    applies_to="optionable",
)
