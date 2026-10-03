# ADR 0002: Decide at close, fill at next open

**Status:** accepted

## Context
Filling at the same close that generated the signal is the most common source of
look-ahead bias in daily backtests.

## Decision
Strategies decide at the close of bar `t`. Market orders fill at the open of bar `t+1`,
with adverse slippage, commission, and buying power checked at the actual fill price.
Sells execute before buys. Orders decided on the last bar never fill.

## Consequences
- Results are more conservative and closer to what is achievable live.
- Overnight gaps can make a target unaffordable; the broker trims the buy rather than
  letting cash go negative.
- Intraday strategies will need a different bar resolution but the same rule.
