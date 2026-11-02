"""``OptionSetup`` (ADR 0088, plan O1): thin types over
``services/read/evaluation/positions/option_setup.py``, and the ``edgeOptionSetup`` field of the
root ``Query`` (a mixin of it, to keep ``query.py`` under the file cap). Every figure, state and
reason is the read model's; nothing is formatted or derived here."""

from datetime import date
from typing import Self

import strawberry

from algotrade.services.read.evaluation.positions import option_evidence, option_setup
from algotrade_api.graphql.offload import off_loop
from algotrade_api.graphql.types.evaluation.edge_costs import EdgeCosts
from algotrade_api.graphql.types.instruments.feature import Unknown
from algotrade_api.graphql.types.query_args import Ctx, Day


@strawberry.type(
    description="One leg of the setup's position: `kind` (shares | option), `qty` signed "
    "(negative: sold); for an option its `right` (P | C), `strike` rule (delta | atm | otm_pct) "
    "with its `delta` or `otmPct` (a fraction) and its own `tenorDays` (null: the setup's)"
)
class OptionLegRule:
    kind: str
    qty: int
    right: str | None
    strike: str | None
    delta: float | None
    otm_pct: float | None
    tenor_days: int | None

    @classmethod
    def of(cls, d: option_setup.LegRule) -> Self:
        return cls(
            kind=d.kind, qty=d.qty, right=d.right, strike=d.strike, delta=d.delta,
            otm_pct=d.otm_pct, tenor_days=d.tenor_days,
        )  # fmt: skip


@strawberry.type(
    description="The option position the setup's document declares: its `template` and `legs`, "
    "the `collateral` rule (cash_secured | max_loss | regt), `schedule` (when it decides), "
    "`startOffsetSessions` (entry that many sessions after the decision), `tenorDays` sought, "
    "`expiryCycle`, `skipReportInLife`, the declared exits (`takeProfit` a share of the credit, "
    "`stopLoss` a multiple of it, `exitDte` calendar days to expiry, `exitConditionFields` the "
    "catalogue fields of its exit condition; null: not declared), the parameters chosen by case "
    "for each pick (`caseValued`, never given a value here)"
)
class OptionRules:
    template: str
    legs: list[OptionLegRule]
    collateral: str
    schedule: str
    start_offset_sessions: int
    tenor_days: int | None
    expiry_cycle: str
    skip_report_in_life: bool
    take_profit: float | None
    stop_loss: float | None
    exit_dte: int | None
    exit_condition_fields: list[str]
    case_valued: list[str]

    @classmethod
    def of(cls, d: option_setup.OptionRules) -> Self:
        return cls(
            template=d.template, legs=[OptionLegRule.of(x) for x in d.legs],
            collateral=d.collateral, schedule=d.schedule,
            start_offset_sessions=d.start_offset_sessions, tenor_days=d.tenor_days,
            expiry_cycle=d.expiry_cycle, skip_report_in_life=d.skip_report_in_life,
            take_profit=d.take_profit, stop_loss=d.stop_loss, exit_dte=d.exit_dte,
            exit_condition_fields=list(d.exit_condition_fields),
            case_valued=list(d.case_valued),
        )  # fmt: skip


@strawberry.type(
    description="One year of decision sessions of the setup's own history: its `trades`, the "
    "`typical` return on the cash set aside (the median, a fraction) and how many trades `kept` "
    "the premium"
)
class OptionYear:
    year: int
    trades: int
    typical: float | None
    kept: int

    @classmethod
    def of(cls, d: option_evidence.OptionYear) -> Self:
        return cls(year=d.year, trades=d.trades, typical=d.typical, kept=d.kept)


@strawberry.type(
    description="One reference stress episode the session knows, from its `start` (the peak) to "
    "its `end` (the trough): how many of the setup's `trades` were open in it and the `worst` "
    "return on the cash set aside among them (null with 0 trades: none was open)"
)
class OptionStressWindow:
    key: str
    name: str
    start: date
    end: date
    trades: int
    worst: float | None

    @classmethod
    def of(cls, d: option_evidence.StressWindow) -> Self:
        return cls(key=d.key, name=d.name, start=d.start, end=d.end, trades=d.trades, worst=d.worst)


@strawberry.type(
    description="What the setup's own history says on the cash it sets aside, from its stored "
    "trades at the verdict's basis (`basisScreener`, `basisHorizon`) as the session knew them; "
    "returns are fractions of the collateral at the document's cost. `typical` the median "
    "trade with its quartiles `typicalLo` / `typicalHi`; `badMean` the mean of the worst "
    "`badTrades` of `trades` (the worst 5%); `kept`: trades of `trades` that returned above "
    "zero; `costs` the stored cost levels (middle price, worse side, full spread: `level`, "
    "`meanRoc`); `byYear` and `stress` (the worst trade open in each reference episode; "
    "`stressUnknown` says why it is empty). `unknown`: why there is no section at all (every "
    "figure null); `inSampleOnly`: only in-sample trades are read. No verdict is made here"
)
class OptionEvidence:
    unknown: Unknown | None
    basis_screener: str | None
    basis_horizon: int | None
    trades: int
    typical: float | None
    typical_lo: float | None
    typical_hi: float | None
    bad_mean: float | None
    bad_trades: int
    kept: int
    costs: EdgeCosts | None
    by_year: list[OptionYear]
    stress: list[OptionStressWindow]
    stress_unknown: Unknown | None
    in_sample_only: bool

    @classmethod
    def of(cls, d: option_evidence.OptionEvidence) -> Self:
        return cls(
            unknown=Unknown.of(d.unknown) if d.unknown is not None else None,
            basis_screener=d.basis_screener, basis_horizon=d.basis_horizon, trades=d.trades,
            typical=d.typical, typical_lo=d.typical_lo, typical_hi=d.typical_hi,
            bad_mean=d.bad_mean, bad_trades=d.bad_trades, kept=d.kept,
            costs=EdgeCosts.of(d.costs) if d.costs is not None else None,
            by_year=[OptionYear.of(y) for y in d.by_year],
            stress=[OptionStressWindow.of(w) for w in d.stress],
            stress_unknown=Unknown.of(d.stress_unknown) if d.stress_unknown is not None else None,
            in_sample_only=d.in_sample_only,
        )  # fmt: skip


@strawberry.type(
    description="The option setup page of an edge (ADR 0088): `positionKind` (shares | options); "
    "for an option setup its declared `rules` and its `evidence`; a share setup has neither "
    "(`rulesUnknown` says so, `evidence` is null)"
)
class OptionSetup:
    edge_id: str
    position_kind: str
    rules: OptionRules | None
    rules_unknown: Unknown | None
    evidence: OptionEvidence | None

    @classmethod
    def of(cls, d: option_setup.OptionSetup) -> Self:
        return cls(
            edge_id=d.edge_id, position_kind=d.position_kind,
            rules=OptionRules.of(d.rules) if d.rules is not None else None,
            rules_unknown=Unknown.of(d.rules_unknown) if d.rules_unknown is not None else None,
            evidence=OptionEvidence.of(d.evidence) if d.evidence is not None else None,
        )  # fmt: skip


@strawberry.type
class OptionSetupQuery:
    @strawberry.field(  # type: ignore[untyped-decorator]
        description="The option setup page of the edge `id` for the session: its declared "
        "option position as rules and its evidence on the cash set aside, from the canonical "
        "run's stored trades as the session knew them (ADR 0088). A share setup has "
        "`positionKind` shares and no sections. Null: no such edge for the viewer (or its "
        "evidence is under a licence they lack), or nothing stored"
    )
    async def edge_option_setup(self, info: Ctx, id: str, date: Day = None) -> OptionSetup | None:
        ctx = await info.context.aread(date)
        found = await off_loop(option_setup.load_option_setup, ctx, id) if ctx is not None else None
        return OptionSetup.of(found) if found is not None else None
