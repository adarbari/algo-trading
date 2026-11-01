"""The common trade contract (ADR 0088, design 2.5a): ``TRADE_COLUMNS``, the one frozen column
set every outcome shape maps to, with its enums, the capital basis of an edge and the validator
the tests use.

A trade is one name (or one book) over one window: its entry and exit, the value and hit the
harness scored (``hit.apply_outcome``), the capital its return is measured on, the return on
capital before cost and at the document's cost, the worst loss as a share of capital, the
underlying's own return, the price source and the outcome row's licence. A figure not known is
null, never 0: every column from ``capital`` to ``underlying_return`` is null on an excluded row,
and a non-finite input gives null.

``max_adverse`` is not one measure across shapes: a share's is the window's intraday dip
(``fwd_max_drawdown``), an option's the worst mark loss at closes only (``structure_pnl@v2``);
a consumer must not pool them without saying so."""

from typing import NamedTuple

import numpy as np
import pandas as pd

from algotrade.config.edges.document import Edge
from algotrade.config.edges.positions.chain import CHAIN_KIND
from algotrade.core.model.errors import ConfigurationError

BARS, MODEL = "bars", "model"
PRICE_SOURCES_ALL = (BARS, MODEL, "cboe", "option_history")
CAPITAL_BASES = ("notional", "cash_secured", "max_loss", "regt", "book", "none")
SIDES = ("long", "short")
BOOK_ID = "BOOK"
HORIZON, DELISTED = "HORIZON", "DELISTED"


class TradeColumn(NamedTuple):
    name: str
    dtype: str  # the storage spec's dtype words: string, float64, date, bool
    nullable: bool


TRADE_COLUMNS: tuple[TradeColumn, ...] = (
    TradeColumn("instrument_id", "string", False),  # the name (a book: BOOK_ID)
    TradeColumn("side", "string", False),  # long / short
    TradeColumn("entry_session", "date", False),  # S
    TradeColumn("exit_session", "date", True),  # a share: S + h sessions; an option: its own
    TradeColumn("exit_kind", "string", True),  # HORIZON / DELISTED, or an option's; null excluded
    TradeColumn("value", "float64", True),  # apply_outcome's, of the side's view
    TradeColumn("higher_is_better", "bool", False),
    TradeColumn("hit", "bool", False),  # False when excluded, as the harness has it
    TradeColumn("excluded", "string", False),  # the harness's reason, "" when counted
    TradeColumn("delisted", "bool", False),
    TradeColumn("capital_basis", "string", False),  # CAPITAL_BASES
    TradeColumn("capital", "float64", True),  # an option's collateral ($ per unit)
    TradeColumn("return_on_capital_gross", "float64", True),  # before any cost
    TradeColumn("return_on_capital", "float64", True),  # at the document's cost_bps
    TradeColumn("max_adverse", "float64", True),  # >= 0: the worst loss as a share of capital
    TradeColumn("underlying_return", "float64", True),  # the name's own fwd_return
    TradeColumn("price_source", "string", False),  # PRICE_SOURCES_ALL
    TradeColumn("outcome_licence", "string", False),  # the outcome row's licence
)
COLUMN_NAMES = tuple(c.name for c in TRADE_COLUMNS)
FIGURES = COLUMN_NAMES[COLUMN_NAMES.index("capital") : COLUMN_NAMES.index("underlying_return") + 1]
_PANDAS = {"string": "object", "float64": "float64", "date": "object", "bool": "bool"}


def capital_basis_of(edge: Edge) -> str:
    """The capital basis of ``edge``'s trades: an option position's collateral rule, ``none`` for
    a hit rate with no money (``expires_otm``, ``hit_target``), ``notional`` for shares and the
    model P&L. A ``portfolio_return`` has none (``shapes.book_trades`` sets ``book``)."""
    o = edge.outcome
    if o.kind == CHAIN_KIND:
        collateral = o.position.collateral if o.position is not None else ""
        if collateral not in CAPITAL_BASES[:4]:
            raise ConfigurationError(f"{edge.id}: an option_pnl position has no collateral rule")
        return collateral
    if o.kind in ("expires_otm", "hit_target"):
        return "none"
    if o.kind in ("excess_return", "option_model_pnl", "pair_spread"):
        return "notional"
    raise ConfigurationError(f"{edge.id}: no capital basis for the outcome {o.kind!r}")


def empty_trades() -> pd.DataFrame:
    """A frame with the contract's columns and no row."""
    return pd.DataFrame({c.name: pd.Series(dtype=_PANDAS[c.dtype]) for c in TRADE_COLUMNS})


def trade_problems(frame: pd.DataFrame) -> list[str]:
    """What is wrong with ``frame`` as trades (empty: nothing): the columns and their order, the
    enums, a null in a column that is never null, a figure on an excluded row."""
    if list(frame.columns) != list(COLUMN_NAMES):
        return [f"columns {list(frame.columns)} are not the contract's {list(COLUMN_NAMES)}"]
    out: list[str] = []
    for c in TRADE_COLUMNS:
        if not c.nullable and frame[c.name].isna().any():
            out.append(f"{c.name} is null")
    for name, allowed in (
        ("side", SIDES), ("capital_basis", CAPITAL_BASES), ("price_source", PRICE_SOURCES_ALL),
    ):  # fmt: skip
        bad = set(frame[name]) - set(allowed)
        if bad:
            out.append(f"{name} has {sorted(bad)}")
    excluded = frame["excluded"].astype(str) != ""
    for name in FIGURES:
        if frame.loc[excluded, name].notna().any():
            out.append(f"{name} is set on an excluded row")
    for name in ("value", *FIGURES):
        numbers = pd.to_numeric(frame[name], errors="coerce").to_numpy(dtype=float)
        if np.isinf(numbers).any():
            out.append(f"{name} is not finite")
    return out
