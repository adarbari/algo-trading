# ADR 0021: Option pricing conventions

**Status:** accepted (2026-10-03; phase 2b.1). Extends [0012](0012-data-vendors.md) and
[0014](0014-cboe-options-source.md) ("we compute Greeks ourselves"). Code: `src/algotrade/quant/`
(pure numerics), `src/algotrade/data/rates.py`, the `rates` ingestion task.

## Context
Phase 2b computes implied volatility and Greeks from stored chains, realised volatility from
bars, and needs a risk-free rate for both. Each choice below (model, time to expiry, rate,
dividend yield, what a failed IV looks like) changes every number downstream, so it is fixed
once here and implemented once, in a new pure library layer `algotrade.quant`.

## Decision

### Model
- **Black-Scholes-Merton for European exercise**, with a continuous risk-free rate `r` and a
  continuous dividend yield `q` (`quant/black_scholes.py`). US equity options are American;
  until an American model is justified, IV is the European-equivalent vol and early
  exercise (deep ITM puts, calls before ex-dates) shows up as `BELOW_INTRINSIC` or a
  slightly higher IV, not as a silent error.
- **Time to expiry** in years = calendar days to expiry / **365** (the option expires at
  the close of its expiry date; intraday time is ignored at end-of-day). Realised vol is
  annualised with **252** trading sessions.
- **Greeks are raw derivatives**: `vega` per 1.00 of vol, `theta` per year (`-dV/dt`),
  `rho` per 1.00 of rate. Divide by 100 / 365 / 100 to compare with vendor columns quoted per
  vol point, per day and per rate point (Cboe's `delta`, `gamma`, `theta`, `vega` on
  `chains/option_quotes` are the vendor's and are kept as a cross-check only).
- **Dividend yield** `q` = trailing-12-month cash dividends (`events/dividend`, by ex-date) /
  the underlying's price on the session, as a continuous yield. Computing it lands with the
  IV rollup (2b.3); until then callers pass `q` explicitly (0 for non-payers).
- The normal CDF is `0.5 * erfc(-x / sqrt 2)` (exact in the tails), numpy only; no scipy.

### Implied volatility
`quant/implied_vol.py`: a safeguarded Newton iteration on price, bracketed in
**[1e-4, 5.0]**, vectorised. The root stays bracketed (price rises with vol); Newton steps are
taken while they land inside the bracket and keep halving it, otherwise the step bisects.
Prices are matched within `1e-10 × strike`. Every element gets a status, and a failure is
**NaN plus a reason code**, never a clipped number:

| Code | Meaning |
|---|---|
| `OK` | solved |
| `BAD_INPUT` | non-finite input, spot / strike / time <= 0, or a negative price |
| `BELOW_INTRINSIC` | price below the discounted forward intrinsic value (no-arbitrage lower bound) |
| `AT_INTRINSIC` | price equals that bound within tolerance: no time value, so no vol |
| `ABOVE_MAX` | price at or above `S e^{-qt}` (calls) / `K e^{-rt}` (puts) |
| `VOL_BELOW_MIN` / `VOL_ABOVE_MAX` | inside the bounds, but the vol is outside [1e-4, 5] |
| `NO_CONVERGENCE` | iteration limit (bisection guarantees convergence first; a safety net) |

Which price is inverted (mid, or bid and ask separately) is the IV rollup's choice (2b.3).

### Realised volatility
`quant/realized_vol.py`: close-to-close (sample stdev of log returns), Parkinson,
Garman-Klass and Yang-Zhang over a rolling window that ENDS at each session (point in time),
annualised by `sqrt(252)`, NaN until the window is full.

### Rates
- **Source:** the U.S. Treasury daily par yield curve (official, free, no key), stored as
  `rates/treasury`: one partition per curve date, one row per tenor (`tenor` such as `1M`,
  `1.5M`, `10Y`; `tenor_days`; `rate_par` and `rate_cont` as decimals; id `RATE:UST-<tenor>`,
  a new `AssetClass.RATE`). A new grain, `curve`: a snapshot of a whole curve per date.
- **Tenor days** = `round(months × 365.25 / 12)` (1M = 30, 3M = 91, 6M = 183, 1Y = 365).
- **Par → continuous:** up to half a year Treasury yields are bond-equivalent simple interest
  (actual/365), `r = ln(1 + y τ) / τ`; beyond, semi-annual compounding, `r = 2 ln(1 + y/2)`.
  Coupon-tenor par yields are used as zero rates without bootstrapping (a few basis points;
  bootstrapping is deferred until a use needs long-dated precision).
- **Interpolation:** linear in the continuous rate against years, flat outside the quoted
  tenors. `data.rates.curve(reader, on)` picks the curve with the one snapshot rule (latest on
  or before `on`, else the earliest, flagged `pre_snapshot`): the bond market has holidays the
  stock market does not, so an exchange session may use the previous curve.

| Alternative | Rejected because |
|---|---|
| scipy (`norm.cdf`, `brentq`) | a heavy dependency for two functions; numpy + `math.erfc` is exact enough and vectorises |
| Vendor IV / Greeks (Cboe) | unknown model and inputs; ADR 0014 already chose to compute our own |
| Binomial / American model now | slower, and no use yet needs early-exercise premia; revisit with the VRP screener |
| SOFR / FRED rates | Treasury is official, keyless, and has the whole term structure in one request per year |
| Trading-day time to expiry | calendar time is what rates and dividends accrue on; one convention for all options |

## Consequences
- `algotrade.quant` sits beside `storage` and `config` in the layer stack, imports only numpy
  (and `core`), and is importable by strategies and screeners (import-linter contracts
  "Layout: quant is pure numeric code" and "Strategies and screeners are pure: they only see
  core and quant"). Ownership: `option-pricing`, `implied-vol`, `realized-vol`,
  `rate-conventions` (quant), `rates-reads` (`data/rates.py`), `[[table]] rates/treasury`
  (`tasks/market/rates.py`).
- Stored IV and Greeks (2b.3) carry the status code alongside the value, so screens can
  exclude or report failures instead of treating NaN as missing data.
