"""Run overlays (ADR 0049): rules the backtest engine applies to every strategy's target
weights after ``on_bar`` and before the risk limits, from the session's market-wide features
(the regime's size multiplier and pauses), so no strategy carries a market-wide rule itself."""
