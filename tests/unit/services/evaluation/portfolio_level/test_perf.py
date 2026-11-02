"""One portfolio row over a busy book is far under the plan's 0.05 s per decision session
(E15; the plan's figure was an estimate, this is the measure)."""

from datetime import date, timedelta
from time import perf_counter

from algotrade.services.evaluation.portfolio_level.book import OpenTrade, portfolio_row

BUDGET_S = 0.05


def test_a_row_over_500_trades_costs_under_the_budget() -> None:
    day = date(2026, 6, 1)
    trades = [
        OpenTrade(f"EQ:{i % 120}", day - timedelta(days=i % 20), day + timedelta(days=1 + i % 9),
                  None, 1000.0, "open")
        for i in range(500)
    ]  # fmt: skip
    sectors = {f"EQ:{i}": f"s{i % 11}" for i in range(120)}
    portfolio_row(trades, day, sectors, option=True)  # warm up
    start = perf_counter()
    for _ in range(20):
        portfolio_row(trades, day, sectors, option=True)
    per_row = (perf_counter() - start) / 20
    assert per_row < BUDGET_S, per_row
