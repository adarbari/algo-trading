"""Bounded short-window momentum oscillator feature groups from daily bars (Cutler's RSI over a
few sessions). Each group is one module: its ``FEATURES``, a pure ``compute`` and its ``GROUP``
declaration (core, quant, numpy and pandas only; no storage, data, config or services)."""
