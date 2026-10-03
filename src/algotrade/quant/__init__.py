"""Pure quantitative finance: option pricing, implied volatility, realised volatility, rates.

Numeric code only (numpy), vectorised over arrays, with no storage, data, config or pandas
imports (import-linter: "Layout: quant is pure numeric code"). Conventions (model, time to
expiry, rates, dividend yield, IV failure codes) are ADR 0021:

- ``black_scholes``  European Black-Scholes-Merton price and Greeks (continuous q and r)
- ``implied_vol``    the IV solver (safeguarded Newton), NaN + a status code on failure
- ``realized_vol``   close-to-close, Parkinson, Garman-Klass, Yang-Zhang (annualised, 252)
- ``rates``          Treasury par yields -> continuous rates; yield-curve interpolation

Strategies, screeners and features may import this package; it imports only ``numpy``.
"""
