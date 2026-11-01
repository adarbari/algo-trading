"""The trades of a window (ADR 0088, design 2.4, 2.4a, 2.5), pure over the stored chains of its
sessions: for an entry session S, a position's legs and an ordered exit rule list, each underlying
with a usable chain at S is entered at S's close and held to the first exit that acts or to the
window's end T (the hold cap).

``select_window`` chooses every name's contracts from S's chain alone (``select_legs`` per name,
the window's end as the floor of the expiry). ``walk_trades`` marks the window (``mark_window``),
computes each close's position-level fields (``walk_fields``) beside the catalogue fields the
caller read from that close's own partition, scans the exit rules (``scan_exits``: an UNKNOWN rule
never fires, its closes are counted) and values each trade at its own exit: names that exit before
T are marked again over the shorter window, so an exit at close k is priced from closes S..k only.
A trade that reaches T with every leg expiring on it is ``EXPIRED`` (or ``ASSIGNED``: an
in-the-money American short, ``settlement.expiry_kind``) and valued at intrinsic; any other is
``HORIZON``. A name
is UNMEASURED with a reason and no exit or P&L when a session it needs lacks a chain or quote (never
filled from an earlier session) or its legs could not be chosen.

Units are per share of one contract: an option leg's quantity is contracts, a share leg's quantity
is shares and counts ``qty / 100``, so a covered call's stock leg is one share beside one call. The
position-level fields the exit rules read (``position.*``) and ``max_adverse`` measure the option
legs' marks; the stock leg's P&L is in ``stock_pnl`` and ``pnl_mid`` (a named follow-up: E4b)."""

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date

import numpy as np
import pandas as pd

from algotrade.config.edges.positions.spec import ExitRule
from algotrade.config.edges.positions.templates import OPTION, SHARES, Leg
from algotrade.core.model.fields import position_field
from algotrade.core.model.predicates import FieldValue
from algotrade.engines.structures.chain import DayChain, Labels
from algotrade.engines.structures.exits import ExitScan, scan_exits
from algotrade.engines.structures.marking import (
    LegColumn,
    Marks,
    Window,
    leg_quotes,
    mark_window,
    years,
)
from algotrade.engines.structures.position_fields import CloseFacts, EntryFacts, Short, walk_fields
from algotrade.engines.structures.settlement import ASSIGNED, EXPIRED, expiry_kind
from algotrade.features.rollups.options.wing_search import LegSelection, select_legs
from algotrade.quant.edges.chain_pnl import hedged_pnl, intrinsic, leg_greeks, position_sum

HORIZON = "HORIZON"
TRADING_DAYS = 252
SHARES_PER_CONTRACT = 100
NAN = float("nan")
type Fields = Mapping[str, Mapping[str, FieldValue]]  # name -> catalogue field -> value at a close


def select_window(
    entry: DayChain, legs: Sequence[Leg], tenor_days: int, expiry_cycle: str, end: date
) -> dict[str, LegSelection]:
    """Each name with an ``OK`` chain at the entry session -> its chosen option legs, or the reason
    it has none (``NO_EXPIRY``, ``NO_ENTRY_QUOTE``), from the entry session's quotes alone; ``end``
    (T) is the floor of every expiry. Names without an ``OK`` label have no entry."""
    ok = sorted(i for i, label in entry.labels.items() if label == Labels().ok)
    found: dict[str, LegSelection] = {}
    quotes = entry.options
    by_name = {} if quotes is None or quotes.empty else dict(iter(quotes.groupby("underlying_id")))
    for name in ok:
        spot = entry.spots.get(name, NAN)
        chain = by_name.get(name)
        if not np.isfinite(spot):
            found[name] = LegSelection(reason="NO_ENTRY_QUOTE")  # no quote prices no strike
        elif chain is None:
            found[name] = LegSelection(reason="NO_EXPIRY")
        else:
            found[name] = select_legs(
                chain, legs, float(spot), entry.day, tenor_days, expiry_cycle, not_before=end
            )
    return found


@dataclass
class Trade:
    """One name's trade: the legs as aligned lists (the share legs included, in template order), the
    entry, the exit and the P&L; a float is NaN where it cannot be computed (never a zero);
    ``reason`` is set (and every exit and P&L field empty) when the trade is UNMEASURED."""

    name: str
    reason: str | None = None
    exit_index: int = 0  # the index in the window's sessions (S = 0) the trade ends at
    kinds: list[str] = field(default_factory=list)
    contract_ids: list[str | None] = field(default_factory=list)
    rights: list[str | None] = field(default_factory=list)
    strikes: list[float | None] = field(default_factory=list)
    expiries: list[date | None] = field(default_factory=list)
    qty: list[float] = field(default_factory=list)
    leg_mid: list[float | None] = field(default_factory=list)
    leg_half_spread: list[float | None] = field(default_factory=list)
    leg_delta: list[float | None] = field(default_factory=list)
    entry_spot: float = NAN
    entry_net_mid: float = NAN
    entry_half_spread: float = NAN
    entry_spread_share: float = NAN
    entry_oi_min: float = NAN
    delta: float = NAN
    gamma: float = NAN
    vega: float = NAN
    theta: float = NAN
    collateral: float = NAN
    notional: float = NAN
    exit_session: date | None = None
    exit_kind: str | None = None
    exit_basis: str | None = None
    exit_net_mid: float = NAN
    exit_half_spread: float = NAN
    expired_otm: bool | None = None
    unknown_closes: int = 0
    pnl_mid: float = NAN
    option_pnl: float = NAN
    stock_pnl: float = NAN
    pnl_hedged_mid: float = NAN
    path_min: float = NAN
    max_adverse: float = NAN
    realised_vol: float = NAN
    mark_mid: list[float | None] | None = None
    spot_path: list[float | None] | None = None


@dataclass(frozen=True)
class _Cohort:
    """The selected names of a window, vectorised for ``mark_window``: ``window`` holds the option
    legs; ``picks`` the chosen legs per name in the same order."""

    names: list[str]
    window: Window
    picks: list[LegSelection]
    option_legs: list[Leg]

    def slice(self, idx: np.ndarray) -> "_Cohort":
        legs = [
            LegColumn(
                c.right, c.qty, c.ids.iloc[idx].reset_index(drop=True), c.strike[idx],
                c.expiry.iloc[idx].reset_index(drop=True),
            )
            for c in self.window.legs
        ]  # fmt: skip
        n = len(idx)
        window = Window(
            self.window.names.iloc[idx].reset_index(drop=True), legs, np.ones(n, bool),
            np.full(n, None, object), np.full(n, None, object),
        )  # fmt: skip
        return _Cohort(
            [self.names[i] for i in idx], window, [self.picks[i] for i in idx], self.option_legs
        )


def _cohort(selected: Mapping[str, LegSelection], legs: Sequence[Leg]) -> _Cohort:
    option_legs = [leg for leg in legs if leg.kind == OPTION]
    names = [n for n, sel in selected.items() if sel.reason is None]
    picks = [selected[n] for n in names]
    columns = []
    for j, leg in enumerate(option_legs):
        chosen = [p.legs[j] for p in picks]
        columns.append(
            LegColumn(
                str(leg.right), float(leg.qty), pd.Series([c.instrument_id for c in chosen]),
                np.array([c.strike for c in chosen], float), pd.Series([c.expiry for c in chosen]),
            )
        )  # fmt: skip
    n = len(names)
    window = Window(
        pd.Series(names), columns, np.ones(n, bool), np.full(n, None, object),
        np.full(n, None, object),
    )  # fmt: skip
    return _Cohort(names, window, picks, option_legs)


def _share_qty(legs: Sequence[Leg]) -> float:
    """Share-equivalents of the position's share legs (signed): 100 shares are one."""
    return sum(leg.qty for leg in legs if leg.kind == SHARES) / SHARES_PER_CONTRACT


def _max_loss(options: Sequence[tuple[float, bool, float]], net_mid: float) -> float:
    """The worst loss at expiry of option legs ``(qty, is_call, strike)`` bought for ``net_mid``
    (negative: a credit): the payoff is piecewise linear, so its minimum is at 0 or a strike;
    NaN when the loss is unbounded (a net short call side) or the entry price is unknown."""
    if not np.isfinite(net_mid) or sum(q for q, c, _ in options if c) < 0:
        return NAN

    def payoff(spot: float) -> float:
        return sum(q * float(intrinsic(spot, k, c)) for q, c, k in options) - net_mid

    return max(0.0, -min(payoff(s) for s in (0.0, *sorted({k for _, _, k in options}))))


def collateral_of(
    kind: str, legs: Sequence[Leg], pick: LegSelection, spot: float, net_mid: float
) -> float:
    """The capital a return is measured on, per share of one contract (design 2.4): ``notional``
    the shares' value, ``cash_secured`` the strike times the short puts, ``max_loss`` the worst
    loss at expiry; ``regt`` is not computed in this slice (NaN, stored null)."""
    if kind == "notional":
        shares = abs(_share_qty(legs))
        return shares * spot if shares else NAN  # no share leg: no notional capital (never 0)
    chosen = [(c.leg.qty, c.leg.right == "C", c.strike) for c in pick.legs]
    if kind == "cash_secured":
        puts = [abs(q) * k for q, call, k in chosen if q < 0 and not call]
        return float(sum(puts)) if puts else NAN
    if kind == "max_loss":
        return _max_loss(chosen, net_mid)
    return NAN


def _open_interest(entry: DayChain, cohort: _Cohort) -> np.ndarray:
    """The lowest open interest among each name's option legs at the entry (NaN: none stored)."""
    n = len(cohort.names)
    options = entry.options
    if options is None or options.empty or "open_interest" not in options.columns:
        return np.full(n, np.nan)
    stored = options.drop_duplicates("instrument_id").set_index("instrument_id")["open_interest"]
    per_leg = [
        stored.reindex(leg.ids.to_numpy()).astype(float).to_numpy() for leg in cohort.window.legs
    ]
    return np.nanmin(np.vstack(per_leg), axis=0) if per_leg else np.full(n, np.nan)


def _entries(
    cohort: _Cohort, entry: DayChain, legs: Sequence[Leg], collateral: str, marks: Marks
) -> list[Trade]:
    """A ``Trade`` per selected name with its legs, entry prices, Greeks and collateral."""
    window = cohort.window
    quotes = [leg_quotes(entry, leg.ids) for leg in window.legs]
    spots = marks.spots[0]
    per_leg = [
        leg_greeks(
            q["mid"].to_numpy(), spots, leg.strike, years(leg.expiry, entry.day), leg.right == "C"
        )
        for q, leg in zip(quotes, window.legs, strict=True)
    ]
    qty = [leg.qty for leg in window.legs]
    position = [
        position_sum(qty, np.vstack([getattr(g, f) for g in per_leg]))
        for f in ("delta", "gamma", "vega", "theta")
    ]
    oi = _open_interest(entry, cohort)
    share = _share_qty(legs)
    trades = []
    for i, name in enumerate(cohort.names):
        trade = Trade(name)
        spot, net = float(spots[i]), float(marks.entry_mid[i])
        option = 0
        for leg in legs:
            trade.kinds.append(leg.kind)
            trade.qty.append(float(leg.qty))
            if leg.kind == SHARES:
                for column in (trade.contract_ids, trade.rights, trade.strikes, trade.expiries):
                    column.append(None)
                trade.leg_mid.append(spot)
                trade.leg_half_spread.append(None)
                trade.leg_delta.append(1.0)
                continue
            chosen = cohort.picks[i].legs[option]
            width = float(quotes[option]["ask"].iloc[i] - quotes[option]["bid"].iloc[i])
            trade.contract_ids.append(chosen.instrument_id)
            trade.rights.append(str(leg.right))
            trade.strikes.append(chosen.strike)
            trade.expiries.append(chosen.expiry)
            trade.leg_mid.append(chosen.mid)
            trade.leg_half_spread.append(width / 2 if np.isfinite(width) else None)
            delta = float(per_leg[option].delta[i])
            trade.leg_delta.append(delta if np.isfinite(delta) else None)
            option += 1
        trade.entry_spot, trade.entry_net_mid = spot, net
        spread = float(marks.entry_exec[i] - marks.entry_mid[i])
        gross = sum(
            abs(leg.qty) * c.mid
            for leg, c in zip(cohort.option_legs, cohort.picks[i].legs, strict=True)
        )
        trade.entry_half_spread = spread
        trade.entry_spread_share = 2 * spread / gross if gross > 0 else NAN
        trade.entry_oi_min = float(oi[i])
        trade.delta, trade.gamma, trade.vega, trade.theta = (float(p[i]) for p in position)
        trade.delta += share
        trade.collateral = collateral_of(collateral, legs, cohort.picks[i], spot, net)
        contracts = sum(abs(leg.qty) for leg in cohort.option_legs)
        trade.notional = spot * (abs(share) + contracts)  # the stock one unit controls
        trades.append(trade)
    return trades


def _position_fields(
    cohort: _Cohort, i: int, marks: Marks, days: Sequence[DayChain], share: float, trade: Trade
) -> list[dict[str, FieldValue]]:
    """``position.*`` at each close after the entry for name ``i``, from its marks (empty when
    the entry price or spot is unknown: no rule can be read)."""
    if not (np.isfinite(trade.entry_net_mid) and np.isfinite(trade.entry_spot)):
        return []
    n = len(days) - 1
    chosen = cohort.picks[i].legs
    shorts = tuple(Short(c.strike, str(c.leg.right)) for c in chosen if c.leg.qty < 0)
    collateral = trade.collateral if np.isfinite(trade.collateral) else None
    start = EntryFacts(
        days[0].day, trade.entry_spot, trade.entry_net_mid, collateral, shorts,
        min(c.expiry for c in chosen),
    )  # fmt: skip
    closes = []
    for t in range(1, n + 1):
        value = float(marks.mids[t][i])
        delta = float(marks.deltas[t][i]) if t < n else NAN  # no hedge delta at the last close
        closes.append(
            CloseFacts(
                days[t].day, t, float(marks.spots[t][i]), value if np.isfinite(value) else None,
                delta + share if np.isfinite(delta) else None,
            )
        )  # fmt: skip
    return walk_fields(start, closes)


def _scan(
    rules: Sequence[ExitRule], rows: list[dict[str, FieldValue]], name: str,
    catalogue: Sequence[Fields],
) -> ExitScan:  # fmt: skip
    if not rules or not rows:
        return ExitScan(None, 0)
    closes = [{**row, **catalogue[t].get(name, {})} for t, row in enumerate(rows)]
    return scan_exits(rules, closes)


def _kind(
    cohort: _Cohort, i: int, spot: float, scan: ExitScan, expired: bool
) -> str:  # fmt: skip
    """The ``exit_kind``: the rule that acted, else (every leg expiring at the exit) ``ASSIGNED``
    when an in-the-money American short expires, ``EXPIRED``; else ``HORIZON``."""
    if scan.hit is not None:
        return scan.hit.kind
    if not expired:
        return HORIZON
    kinds = [
        expiry_kind(spot, c.strike, c.leg.right == "C", c.leg.qty < 0, False)
        for c in cohort.picks[i].legs
    ]
    return ASSIGNED if ASSIGNED in kinds else EXPIRED


def _realised_vol(spots: np.ndarray) -> float:
    """Annualised stdev of the daily log returns of ``spots`` (NaN under two returns)."""
    with np.errstate(invalid="ignore", divide="ignore"):
        returns = np.diff(np.log(spots))
    returns = returns[np.isfinite(returns)]
    return float(returns.std(ddof=1) * math.sqrt(TRADING_DAYS)) if len(returns) > 1 else NAN


def _settle(
    trade: Trade, cohort: _Cohort, i: int, j: int, marks: Marks, hedged: float,
    days: Sequence[DayChain], share: float, scan: ExitScan,
    fields: list[dict[str, FieldValue]], reason: str | None, book: bool,
) -> None:  # fmt: skip
    """Value ``trade`` at its exit index (``len(marks.spots) - 1``) from ``marks`` (name ``j``)."""
    k = len(marks.spots) - 1
    trade.exit_index = k
    spots = np.array([s[j] for s in marks.spots], float)
    exit_mid, entry_mid = float(marks.exit_mid[j]), float(marks.entry_mid[j])
    option, stock = exit_mid - entry_mid, share * (spots[k] - spots[0])
    if reason is None and not np.isfinite(option + stock):
        reason = "NO_PNL"
    if reason is not None:
        trade.reason = reason
        return
    expired = bool(marks.at_expiry[j])
    trade.unknown_closes = scan.unknown_closes
    trade.exit_session = days[k].day
    trade.exit_kind = _kind(cohort, i, float(spots[k]), scan, expired)
    trade.exit_basis = "INTRINSIC" if expired else "QUOTE"
    trade.exit_net_mid = exit_mid
    trade.exit_half_spread = exit_mid - float(marks.exit_exec[j])
    if expired:
        out = [
            float(intrinsic(spots[k], c.strike, c.leg.right == "C")) for c in cohort.picks[i].legs
        ]
        trade.expired_otm = not any(v > 0 for v in out)
    trade.option_pnl, trade.stock_pnl, trade.pnl_mid = option, stock, option + stock
    trade.pnl_hedged_mid = hedged
    marked = [
        marks.mids[t][j] + share * spots[t] - (entry_mid + share * spots[0]) for t in range(1, k)
    ]
    # an interior close with no mark leaves the lowest P&L unknown: null, never the min of the rest
    trade.path_min = float(np.min([*marked, option + stock])) if np.isfinite(marked).all() else NAN
    if fields and not share:  # a stock leg's loss is not in the option marks (E4b): null
        worst = fields[k - 1][position_field("mark_loss_share_of_collateral")]
        trade.max_adverse = NAN if worst is None else float(worst)
    trade.realised_vol = _realised_vol(spots)
    if book:
        trade.mark_mid = [float(v) if np.isfinite(v) else None for v in
                          (m[j] for m in marks.mids)]  # fmt: skip
        trade.spot_path = [float(v) for v in spots]


def walk_trades(
    days: Sequence[DayChain], legs: Sequence[Leg], collateral: str,
    selected: Mapping[str, LegSelection], rules: Sequence[ExitRule],
    catalogue: Sequence[Fields], book: bool = False,
) -> list[Trade]:  # fmt: skip
    """The trades of the window ``days`` (S..T in order) for the names of ``selected`` (one per
    name with an ``OK`` chain at S, ``select_window``), in that order: UNMEASURED with a reason
    where the legs could not be chosen or a session lacks what the trade needs.
    ``catalogue[t - 1]`` holds each name's catalogue fields at close ``t`` (read from that close's
    own partition: a rule over them acts one close later); empty entries when no rule names one."""
    labels, n, share = Labels(), len(days) - 1, _share_qty(legs)
    cohort = _cohort(selected, legs)
    done = {name: Trade(name, sel.reason) for name, sel in selected.items() if sel.reason}
    if cohort.names:
        full = mark_window(days, cohort.window, labels)
        trades = _entries(cohort, days[0], legs, collateral, full)
        rows = [_position_fields(cohort, i, full, days, share, t) for i, t in enumerate(trades)]
        scans = [_scan(rules, r, t.name, catalogue) for r, t in zip(rows, trades, strict=True)]
        at: dict[int, list[int]] = {}
        for i, scan in enumerate(scans):
            at.setdefault(scan.hit.at + 1 if scan.hit else n, []).append(i)
        for k, group in at.items():
            idx = np.array(group)
            sub = cohort if k == n else cohort.slice(idx)
            marks = full if k == n else mark_window(days[: k + 1], sub.window, labels)
            first = np.vstack(marks.spots).T
            deltas = np.vstack(marks.deltas).T + share
            hedge = hedged_pnl(
                marks.entry_mid + share * first[:, 0], marks.exit_mid + share * first[:, -1],
                first, deltas,
            )  # fmt: skip
            pairs = list(enumerate(group)) if k < n else [(i, i) for i in group]
            for j, i in pairs:
                reason = sub.window.reason[j]
                _settle(
                    trades[i],
                    cohort,
                    i,
                    j,
                    marks,
                    float(hedge[j]),
                    days,
                    share,
                    scans[i],
                    rows[i],
                    None if pd.isna(reason) else str(reason),
                    book,
                )
        done.update({t.name: t for t in trades})
    return [done[name] for name in selected]
