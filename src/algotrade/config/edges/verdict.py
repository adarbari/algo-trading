"""The thresholds of an edge's verdict (``config/site/verdict.toml``, ED8): how many out-of-sample
trades it takes to say anything, and what Promising and Works ask of the out-of-sample
figures. Data, not code: the rule (``services/read/evaluation/verdict.py``) reads them from
here, and each default is the owner's decision of 2026-10-09."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from algotrade.config.site.fields import Table

KEYS = (
    "min_oos_trades",
    "works_trades",
    "works_oos_trades",
    "not_working_t",
    "promising_t",
    "works_t",
    "not_working_dsr",
    "promising_dsr",
    "works_dsr",
    "max_pbo",
    "works_max_pbo",
    "oos_lift_share",
    "random_beat_share",
    "forward_sessions",
    "live_min_trades",
    "live_low",
    "live_high",
)


@dataclass(frozen=True)
class VerdictSettings:
    """Trades are independent sessions; ``t`` is the top-vs-bottom decile t statistic, ``dsr`` the
    deflated Sharpe ratio, ``pbo`` the probability of backtest overfitting. ``oos_lift_share``:
    the out-of-sample lift must keep this share of the whole-history lift. Works needs the
    out-of-sample lift to beat ``random_beat_share`` of the random-pick backtests' draws (ED8,
    drawn by the harness)."""

    min_oos_trades: int = 40  # owner decision 2026-10-09
    works_trades: int = 100
    works_oos_trades: int = 40
    not_working_t: float = 1.0
    promising_t: float = 2.0
    works_t: float = 3.0
    not_working_dsr: float = 0.5
    promising_dsr: float = 0.80
    works_dsr: float = 0.95
    max_pbo: float = 0.5
    works_max_pbo: float = 0.2
    oos_lift_share: float = 0.5
    random_beat_share: float = 0.95
    forward_sessions: int = 20  # a new version's forward test, in sessions (ED8; owner 2026-10-09)
    # The live record (paper trades) is judged against the backtest's usual range, the ``live_low``
    # to ``live_high`` quantiles of the wins n closed trades would show if the backtest's win rate
    # held, once ``live_min_trades`` have closed (ED8, ADR 0053 amendment; owner-delegated).
    live_min_trades: int = 10
    live_low: float = 0.10
    live_high: float = 0.90

    @classmethod
    def from_document(
        cls, doc: Mapping[str, Any] | None, where: str = "verdict.toml"
    ) -> "VerdictSettings":
        d = cls()
        t = Table(doc, where)
        t.only(KEYS)
        return cls(
            min_oos_trades=t.integer("min_oos_trades", d.min_oos_trades, 1),
            works_trades=t.integer("works_trades", d.works_trades, 1),
            works_oos_trades=t.integer("works_oos_trades", d.works_oos_trades, 1),
            not_working_t=t.number("not_working_t", d.not_working_t),
            promising_t=t.number("promising_t", d.promising_t),
            works_t=t.number("works_t", d.works_t),
            not_working_dsr=t.fraction("not_working_dsr", d.not_working_dsr),
            promising_dsr=t.fraction("promising_dsr", d.promising_dsr),
            works_dsr=t.fraction("works_dsr", d.works_dsr),
            max_pbo=t.fraction("max_pbo", d.max_pbo),
            works_max_pbo=t.fraction("works_max_pbo", d.works_max_pbo),
            oos_lift_share=t.number("oos_lift_share", d.oos_lift_share, 0),
            random_beat_share=t.fraction("random_beat_share", d.random_beat_share),
            forward_sessions=t.integer("forward_sessions", d.forward_sessions, 1),
            live_min_trades=t.integer("live_min_trades", d.live_min_trades, 1),
            live_low=t.fraction("live_low", d.live_low),
            live_high=t.fraction("live_high", d.live_high),
        )
