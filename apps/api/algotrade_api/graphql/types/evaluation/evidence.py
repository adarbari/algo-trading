"""The evidence an edge's verdict rests on, as the graph serves it (ADR 0064, ADR 0065):
``EdgeTradePage`` (the ledger of the verdict's basis, paged and sorted by the server, a
per-name value under a licence the viewer lacks an ``Unknown``) and ``EdgeVariants`` (the grid
of every screen and holding period the run tried, the basis marked). Thin types over
``services/read/edge_evidence``; the CSV file route serves the same loader."""

import datetime as dt
from typing import Self

import strawberry

from algotrade.services.read.edge_ledger import trades, variants
from algotrade.services.read.evaluation import runs, versions
from algotrade_api.graphql.types.instruments.feature import Unknown

strawberry.enum(
    trades.Period,
    name="TradePeriod",
    description="Which trades: IN_SAMPLE and OUT_OF_SAMPLE sides of the backtest, ALL of the "
    "backtest, or LIVE (the paper record)",
)
strawberry.enum(
    trades.Sort, name="TradeSort", description="The column a page of trades is sorted by"
)


@strawberry.type(
    description="A per-name number: `value` (null: not stored, never 0) or, when the viewer may "
    "not read it, `unknown` (LICENCE: a personal-licence source)"
)
class TradeNumber:
    value: float | None
    unknown: Unknown | None

    @classmethod
    def of(cls, d: runs.TradeCell) -> Self:
        unknown = Unknown.of(d.unknown) if d.unknown is not None else None
        return cls(value=None if d.value is None else float(d.value), unknown=unknown)


@strawberry.type(
    description="A per-name text (a ticker, a company name): `value`, or why it is not known "
    "(`unknown`: the name is not in the reference snapshot); never the instrument id"
)
class TradeText:
    value: str | None
    unknown: Unknown | None

    @classmethod
    def of(cls, d: runs.TradeText) -> Self:
        return cls(value=d.value, unknown=Unknown.of(d.unknown) if d.unknown is not None else None)


@strawberry.type(description="A per-name yes / no, as `TradeNumber`")
class TradeFlag:
    value: bool | None
    unknown: Unknown | None

    @classmethod
    def of(cls, d: runs.TradeCell) -> Self:
        unknown = Unknown.of(d.unknown) if d.unknown is not None else None
        return cls(value=None if d.value is None else bool(d.value), unknown=unknown)


@strawberry.type(
    description="One trade of the ledger (a pick of the verdict's basis; excluded picks stay with "
    "their public `excludedReason`): `status` won, lost, excluded, or open (a paper trade not "
    "settled yet); `beforeSplit`: the decision session is in-sample; `source`: backtest or live; "
    "`score` is the score at the decision session; `value` is oriented and net of cost "
    "(null: not stored)"
)
class EdgeTradeRow:
    variant: str
    horizon_sessions: int
    decision_session: dt.date
    entry_session: dt.date | None
    exit_session: dt.date | None
    instrument_id: str
    symbol: TradeText
    company: TradeText
    rank: int | None
    status: str
    excluded_reason: str | None
    hit: bool | None
    delisted: bool
    before_split: bool
    source: str
    score: TradeNumber
    value: TradeNumber
    gross_value: TradeNumber
    max_drawdown: float | None
    adv_usd: TradeNumber
    reference: TradeNumber
    touch: TradeFlag

    @classmethod
    def of(cls, d: runs.TradeRow) -> Self:
        return cls(
            variant=d.variant,
            horizon_sessions=d.horizon_sessions,
            decision_session=d.decision_session,
            entry_session=d.entry_session,
            exit_session=d.exit_session,
            instrument_id=d.instrument_id,
            symbol=TradeText.of(d.symbol),
            company=TradeText.of(d.company),
            rank=d.rank,
            status=d.status,
            excluded_reason=d.excluded_reason,
            hit=d.hit,
            delisted=d.delisted,
            before_split=d.before_split,
            source=d.source,
            score=TradeNumber.of(d.score),
            value=TradeNumber.of(d.value),
            gross_value=TradeNumber.of(d.gross_value),
            max_drawdown=d.max_drawdown,
            adv_usd=TradeNumber.of(d.adv_usd),
            reference=TradeNumber.of(d.reference),
            touch=TradeFlag.of(d.touch),
        )


@strawberry.type(
    description="One page of the trades of the edge's verdict basis (`basis`: its screen and "
    "holding period, never chosen again). `unknown`: why there is no ledger (NOT_RUN: no official "
    "run; PRUNED: re-run the backtest; NOT_STORED: the run is older than the ledger); "
    "`oosHidden`: a copy's out-of-sample trades are withheld, so none is served; `licence`: the "
    "trial licence of the rows; `symbolsSnapshot`: the reference snapshot the tickers come from"
)
class EdgeTradePage:
    period: trades.Period
    page: int
    page_size: int
    total: int
    basis: str | None
    licence: str | None
    oos_hidden: bool
    symbols_snapshot: dt.date | None
    unknown: Unknown | None
    rows: list[EdgeTradeRow]

    @classmethod
    def of(cls, d: trades.EdgeTradePage) -> Self:
        return cls(
            period=d.period,
            page=d.page,
            page_size=d.page_size,
            total=d.total,
            basis=d.basis,
            licence=d.licence,
            oos_hidden=d.oos_hidden,
            symbols_snapshot=d.symbols_snapshot,
            unknown=Unknown.of(d.unknown) if d.unknown is not None else None,
            rows=[EdgeTradeRow.of(r) for r in d.rows],
        )


@strawberry.type(
    description="One period's figures of one variant: `winRate`, `baseRate`, `liftPts` (win rate "
    "minus base rate, in points), `decileSpread` and the independent `trades` behind them "
    "(null: not stored)"
)
class VariantFigures:
    win_rate: float | None
    base_rate: float | None
    lift_pts: float | None
    decile_spread: float | None
    trades: int | None

    @classmethod
    def of(cls, d: versions.Figures) -> Self:
        return cls(
            win_rate=d.win_rate,
            base_rate=d.base_rate,
            lift_pts=d.lift_pts,
            decile_spread=d.decile_spread,
            trades=d.trades,
        )


@strawberry.type(
    description="One screen at one holding period the run tried (`edgeVariant`: `main` for the "
    "edge itself). `official`: the verdict's basis, fixed before the frozen period was read; "
    "`notPreChosen`: it has out-of-sample figures and is not the basis, so they are not the "
    "fair test; `modelFit`: its in-sample figure is a model's training fit"
)
class EdgeVariant:
    edge_variant: str
    variant: str
    horizon_sessions: int
    in_sample: VariantFigures | None
    out_of_sample: VariantFigures | None
    all: VariantFigures | None
    official: bool
    not_pre_chosen: bool
    model_fit: bool

    @classmethod
    def of(cls, d: variants.EdgeTrial) -> Self:
        return cls(
            edge_variant=d.edge_variant,
            variant=d.variant,
            horizon_sessions=d.horizon_sessions,
            in_sample=VariantFigures.of(d.in_sample) if d.in_sample else None,
            out_of_sample=VariantFigures.of(d.out_of_sample) if d.out_of_sample else None,
            all=VariantFigures.of(d.all) if d.all else None,
            official=d.official,
            not_pre_chosen=d.not_pre_chosen,
            model_fit=d.model_fit,
        )


@strawberry.type(
    description="The variant grid of the edge's official run: every screen and holding period it "
    "tried, the verdict's `basis` marked official; `trials` the run's trial count; `oosHidden`: "
    "no out-of-sample figure is served; `unknown`: why there is no grid (NOT_RUN)"
)
class EdgeVariants:
    basis: str | None
    trials: int | None
    oos_hidden: bool
    unknown: Unknown | None
    rows: list[EdgeVariant]

    @classmethod
    def of(cls, d: variants.EdgeTrials) -> Self:
        return cls(
            basis=d.basis,
            trials=d.trials,
            oos_hidden=d.oos_hidden,
            unknown=Unknown.of(d.unknown) if d.unknown is not None else None,
            rows=[EdgeVariant.of(r) for r in d.rows],
        )
