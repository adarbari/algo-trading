"""The pick rows of one session (leg v2, ADR 0064): every pick in rank order, counted or with its
reason (``_picks``), and the null / finite coercions of a stored cell. Split from ``measuring.py``
(at its line cap), behaviour unchanged."""

import math
from collections.abc import Mapping, Sequence
from datetime import date
from typing import Any

import pandas as pd

from algotrade.config.edges.document import Edge
from algotrade.config.edges.identity import LONG, SHORT
from algotrade.config.edges.verdict import OptionCosts
from algotrade.services.evaluation.cross_section.hit import (
    is_return,
    level_rocs,
    level_values,
    own_rows,
    short_view,
)
from algotrade.services.evaluation.cross_section.measures import (
    Pick,
)
from algotrade.services.evaluation.cross_section.reads.entry import Entered
from algotrade.services.evaluation.cross_section.reporting.report_containment import window_end
from algotrade.services.evaluation.evidence.shapes import trade_frame
from algotrade.services.evaluation.evidence.values import figures_by_name

NO_ENTRY_BAR = "no_entry_bar"  # a pick's reason when its name has no outcome row at S


def _picks(
    edge: Edge,
    picks: Sequence[str],
    scores: Mapping[str, float],
    res: pd.DataFrame,
    rows: pd.DataFrame,
    adv: Mapping[str, float | None],
    side: str,
    entry: date | Mapping[str, date],
    exit_on: date | Mapping[str, date],
    levels: Sequence[pd.DataFrame] = (),
    option_costs: OptionCosts | None = None,
    entered: Entered | None = None,
    horizon: int = 0,
) -> tuple[Pick, ...]:
    """Every pick of a session in rank order (leg v2, ADR 0064): counted or with its reason.
    ``res`` is the scored outcomes of the base names, ``rows`` the stored ones at S (the option
    trade grain's hold every edge's position keys: ``own_rows`` picks this edge's); a ``short``
    leg's value and hit are the short's. The contract's fields (leg v5, ADR 0088 2.5a) come from
    ``trade_frame`` over the picks only; ``entry`` is S, ``exit_on`` S + h sessions;
    ``levels``: an option edge's outcomes at each cost level (``values_at``); ``option_costs``: the
    commission its return on capital pays, as the pick value and the base do. ``entered``: an
    entry condition's (each pick's own S and exit, or why it did not enter)."""
    held = entered.reasons if entered is not None else {}
    if entered is not None:  # each name its own S and exit
        entry, exit_on = entered.at, {i: window_end(d, horizon) for i, d in entered.at.items()}
    res = short_view(res) if side == SHORT else res
    rows = own_rows(edge, rows[rows["instrument_id"].isin(set(picks))])
    stored = rows.set_index("instrument_id")
    named = res.loc[[i for i in picks if i in res.index]]
    trades = trade_frame(
        edge, rows, named, entry=entry, bars_exit=exit_on, side=side, option_costs=option_costs
    ).set_index("instrument_id")
    figures = figures_by_name(stored)  # an option's hedged / stock / wing figures (E6b-3)
    gross = is_return(edge)
    out = []
    for rank, i in enumerate(picks, start=1):
        if i not in res.index:  # not entered (its reason), or no row at its S
            why = held.get(i, NO_ENTRY_BAR)
            out.append(Pick(i, rank, why, score=scores.get(i), adv=adv.get(i), side=side))
            continue
        r = res.loc[i]
        counted = r["excluded"] == ""
        out.append(
            Pick(
                instrument_id=i,
                rank=rank,
                reason=str(r["excluded"]),
                value=_finite(r["oriented"]) if counted else None,
                hit=bool(r["hit"]),
                delisted=bool(r["delisted"]),
                score=scores.get(i),
                gross=_finite(stored.at[i, "fwd_excess_return"]) if gross and counted else None,
                drawdown=_finite(stored.at[i, "fwd_max_drawdown"]),
                adv=adv.get(i),
                reference=_finite(r["reference"]),
                touch=None if _finite(r["reference"]) is None else bool(r["touch"]),
                side=side,
                exit_session=_none_if_null(trades.at[i, "exit_session"]),
                exit_kind=_none_if_null(trades.at[i, "exit_kind"]),
                capital=_finite(trades.at[i, "capital"]),
                roc_gross=_finite(trades.at[i, "return_on_capital_gross"]),
                roc=_finite(trades.at[i, "return_on_capital"]),
                adverse=_finite(trades.at[i, "max_adverse"]),
                price_source=str(trades.at[i, "price_source"]),
                outcome_licence=str(trades.at[i, "outcome_licence"]),
                values_at=(leveled := level_values(levels, i) if counted else None),
                rocs_at=level_rocs(leveled, stored, i) if side == LONG else None,  # E11
                entry_session=entry.get(i) if isinstance(entry, Mapping) else None,
                delisting_basis=_none_if_null(r["delisting_basis"]) if counted else None,
                zero_value=_finite(r["zero_value"]) if counted else None,
                zero_hit=bool(r["zero_hit"])
                if counted and _finite(r["zero_value"]) is not None
                else None,
                **(figures.get(i, {}) if counted else {}),
            )
        )
    return tuple(out)


def _none_if_null(value: Any) -> Any:
    return None if pd.isna(value) else value


def _finite(value: object) -> float | None:
    number = None if value is None else float(value)  # type: ignore[arg-type]
    return number if number is not None and math.isfinite(number) else None
