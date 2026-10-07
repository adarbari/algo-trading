"""Bar-shape and candlestick pattern feature groups from daily bars: body and wick shares,
two-bar relations and the named candles a screen thresholds. Each group is one module: its
``FEATURES``, a pure ``compute`` and its ``GROUP`` declaration (core, quant, numpy and pandas
only; no storage, data, config or services)."""
