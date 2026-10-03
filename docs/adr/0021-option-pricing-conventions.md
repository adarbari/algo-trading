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
  the underlying's price on the session, as a continuous yield. Computed by `dividends@v1`
  (see the 2b.3 addendum); callers outside rollups pass `q` explicitly (0 for non-payers).
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

Which price is inverted: the mid (2b.3 addendum).

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

## Addendum (2026-10-03, phase 2b.3): IV30, dividend yield, IV rank

**Owner decisions:** we compute our own IV30 beside Cboe's and use ours by default; IV rank is
PROVISIONAL after 60 sessions of history (flagged with `history_days`) and FULL after 252; the
risk-free rate is the Treasury curve (`data.rates`); the dividend yield is trailing-12-month
dividends / close.

### Dividend yield (`dividends@v1`)
`q = div_ttm / close`, with `div_ttm` the cash dividends whose ex-date is in (session - 365
days, session], each divided by the ratio of every split after its ex-date up to the session
(the close is in the session's share terms, so the dividends must be too). The simple yield is
used directly as the continuous `q` (the difference is second order for yields of a few
percent). Distributions typed `special` are left out (a one-off is not a yield). A non-payer
is 0 only with a year of bars (240 of 252 sessions); otherwise null, and pricing uses `q = 0`.

### IV30 (`iv30@v1`)
A constant-maturity 30-calendar-day at-the-money implied vol, per underlying:

1. **Expiries:** among expiries 7 to 90 days out, the latest at or before 30 days and the
   earliest at or after it, from the standard monthlies when they bracket 30 days, else from
   every listed expiry (weeklies); else the single expiry nearest 30 days (flat vol,
   `SINGLE_EXPIRY`). An expiry exactly 30 days out is used alone.
2. **Forward ATM:** `t = days / 365`, `r = curve(t)`, `F = S e^{(r - q) t}` with `S` the
   underlying quote's price; the two listed strikes around `F` (highest at or below, lowest
   above).
3. **Quotes:** each call and put at those strikes must have bid > 0, ask > bid,
   `(ask - bid) / mid <= 0.35` and open interest >= 10 or volume >= 1 (all in `rollups.toml`).
   The **mid** is inverted with `quant.implied_vol` (this answers "which price is inverted").
4. **ATM vol:** call and put vols averaged per strike (put-call parity makes them equal for a
   European; the average cancels American early-exercise and forward errors to first order),
   then linear in strike to `F`.
5. **Term:** linear in total variance `sigma^2 t` between the two expiries, evaluated at
   30 days (`quant.implied_vol.interpolate_total_variance`), `sigma30 = sqrt(w(t30) / t30)`.

Failures are a null `iv30` plus `iv30_status`: `NO_SPOT`, `NO_CHAIN`, `NO_EXPIRY`,
`NO_QUOTES`, `WIDE_SPREADS`, `ILLIQUID`, `IV_FAILED` (the furthest step an expiry reached).
`iv30_cboe` keeps the feed's value (a percentage, stored as a decimal) for comparison only.

| Alternative | Rejected because |
|---|---|
| Cboe's `iv30` only | unknown method and inputs (ADR 0014); kept as a cross-check column |
| VIX-style variance swap (whole strip of OTM options) | needs deep, clean strips; most single names have a handful of liquid strikes |
| Inverting bid and ask separately | twice the work, and the spread is already filtered; the mid is the market's estimate |
| Linear in vol across expiries | not arbitrage-consistent; total variance is the standard |

### IV rank (`iv_history@v1`)
Rank `(iv - min) / (max - min)` and percentile (share of earlier values strictly below today)
over the last 252 sessions of our IV30 (or Cboe's: `source = "cboe"`). Below 60 sessions with
an IV the status is UNKNOWN and both are null; 60 to 251 PROVISIONAL; 252 FULL.

### Ownership exceptions
`features/rollups/iv30.py` names its input `rates/treasury` (the framework reads it through
`data.rates`), and `features/rollups/dividends.py` is named `dividends` (a rollup, not a
vendor source): both are `allowed` entries in `architecture/ownership.toml` with this reason.
