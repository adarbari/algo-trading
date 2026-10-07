"""Feature groups of volatility and trading activity from daily bars: ATR and realised-vol
windows with their percentiles against the name's own year, longer volume averages and the
volume rank, and volume at price (the daily-bar profile: point of control, value area, high
and low volume nodes). Each group is one module: its ``FEATURES``, a pure ``compute`` and its
``GROUP`` declaration (core, quant, numpy and pandas only; no storage, data, config or
services)."""
