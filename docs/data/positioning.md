# Options positioning features (OP track)

The definitions behind roadmap track OP: dealer gamma and delta exposure, walls, chain flow,
skew and the implied move, all computed nightly from the stored Cboe chains. Decision record:
[ADR 0030](../adr/0030-options-positioning-features.md). Model and catalogue conventions:
[ADR 0023](../adr/0023-feature-store.md), [features.md](features.md); pricing conventions:
[ADR 0021](../adr/0021-option-pricing-conventions.md).

**Status: parked (2026-10-04); the roadmap schedules the smaller SW track instead.** Draft, kept for later. Every choice marked **Proposed** is a
recommendation the owner confirms or changes before OP1 code starts. Once confirmed, the
Proposed markers go and this page becomes the spec the group docstrings point to; the
generated catalogue (`features.md`) then carries the per-feature text.

## What these numbers are, and are not

- **Daily estimates, not observations.** Cboe's `open_interest` is OCC's figure as of the
  previous session's close ([vendors.md](vendors.md#cboe-delayed-quotes-feed-primary-for-options)),
  the quotes are the end-of-day snapshot. So every exposure on session S is "positions at the
  close of S-1, priced at the close of S". Nothing is intraday.
- **No side data.** Open interest says how many contracts exist, not who is long. Every
  gamma figure below assumes a positioning (the dealer convention in [P1](#p1-dealer-sign-convention)).
  It is the industry's standard assumption and it is often wrong for single names (call
  overwriting vs. retail call buying flips it). Treat walls and flips as estimates.
- **Our Greeks.** IV and Greeks come from `quant/` (ADR 0014, 0021): BSM with Treasury `r` and
  `div_yield` `q`, European-equivalent vols on American options. The feed's `iv`, `delta`,
  `gamma` columns are a cross-check only.
- **History starts with the first stored chain** (2026-10-02 on the local store). There is
  nothing to backfill from earlier: ranks over skew stay UNKNOWN for the first 60 sessions.

## Field mapping (third-party panel to our features)

The panel list in the brief has 38 names (52-week high and low counted separately); the
roadmap says 40, see [Q6](#open-questions-for-the-owner).

| Panel field | Ours | Where | Status |
|---|---|---|---|
| Current Price | `price_stats.close` (session close); live price via `GET /chains/{id}/live` | `price_stats@v2` | stored |
| Previous Close | `price_moves.prev_close` | `price_moves@v2` ([below](#prev_close)) | OP0 |
| Stock Volume | `option_liquidity.stock_volume` (feed; optionable names) | `option_liquidity@v1` | stored |
| 52 Week High / Low | `price_stats.high_52w`, `price_stats.low_52w` | `price_stats@v2` | stored |
| Earnings Date | `earnings.next_earnings_date` | `earnings@v1` | stored |
| Key Gamma Strike | `gex.key_gamma_strike` | `gex@v1` | OP1 |
| Key Delta Strike | `gex.key_delta_strike` | `gex@v1` | OP1 |
| Hedge Wall | `gex.gamma_flip` (zero-gamma level, P4) | `gex@v1` | OP1 |
| Call Wall | `gex.call_wall` | `gex@v1` | OP1 |
| Put Wall | `gex.put_wall` | `gex@v1` | OP1 |
| Options Impact | `options_impact` (expression) | positioning.toml | OP1 |
| Call Gamma | `gex.gex_call` | `gex@v1` | OP1 |
| Put Gamma | `gex.gex_put` | `gex@v1` | OP1 |
| Next Exp Gamma | `gex.gex_next_exp` | `gex@v1` | OP1 |
| Next Exp Delta | `gex.dex_next_exp` | `gex@v1` | OP1 |
| Top Gamma Exp | `gex.top_gamma_expiry` | `gex@v1` | OP1 |
| Top Delta Exp | `gex.top_delta_expiry` | `gex@v1` | OP1 |
| Call Volume | `chain_flow.call_volume` | `chain_flow@v1` | OP2 |
| Put Volume | `chain_flow.put_volume` | `chain_flow@v1` | OP2 |
| Next Exp Call Vol | `chain_flow.next_exp_call_volume` | `chain_flow@v1` | OP2 |
| Next Exp Put Vol | `chain_flow.next_exp_put_volume` | `chain_flow@v1` | OP2 |
| Put/Call OI Ratio | `put_call_oi_ratio` (expression) | positioning.toml | OP2 |
| Volume Ratio | `volume_ratio` (expression) | positioning.toml | OP2 |
| Gamma Ratio | `gamma_ratio` (expression) | positioning.toml | OP2 |
| Delta Ratio | `delta_ratio` (expression) | positioning.toml | OP2 |
| NE Skew | `skew.ne_skew` | `skew@v1` | OP3 |
| Skew | `skew.skew` | `skew@v1` | OP3 |
| Skew Rank | `skew_history.skew_rank_252d` | `skew_history@v1` | OP3 |
| 1M RV | `price_stats.hv20` (20 close-to-close log returns) | `price_stats@v2` | stored |
| 1M IV | `iv30.iv30` (ours) | `iv30@v1` | stored |
| IV Rank | `iv_rank` (IBKR's, else ours; personal licence) or `iv_history.iv_rank_252d` (open) | expression / `iv_history@v2` | stored |
| Options Implied Move | `implied_move.implied_move` | `implied_move@v1` | OP4 |
| Garch Rank | `garch.garch_rank_252d` | `garch@v1` | OP5 |
| DPI, % DPI Volume, 5 day DPI, 5d % DPI Volume | none: no source | | OP6 (blocked on a data decision) |

Count: 8 stored, 1 in OP0, 24 in OP1 to OP4, 1 in OP5, 4 in OP6.

## Shared rules (every OP group)

**Inputs.** The session's `chains/option_quotes` and `chains/underlying_quotes`, the Treasury
curve the session sees (`rates/treasury`, one snapshot rule), `div_yield@v1` (missing: `q = 0`),
as `iv30@v1` and `put_wing@v1` read them today. One row per underlying with a chain or an
underlying quote on the session. Licence `open` for every feature here (computed by us from the
Cboe feed and bars).

**Spot (Proposed).** `S0 = chains/underlying_quotes.close` when positive, else `.price`, else
NO_SPOT. Alternative: `.price`, as `iv30` and `put_wing` use. Reason: on 2026-10-02 the feed's
`price` matched the session's bar close for only 71% of names (it carries after-hours trades),
`close` matched for 97%, and option quotes are closing quotes. Mixing an after-hours spot with
closing option quotes moves every ATM strike and every Greek.

**Series.** Only standard roots are stored (`is_standard_root`): adjusted series after an odd
split or a merger (deliverable not 100 shares) are dropped at ingest and counted in the chain
run's `nonstandard_series`. So the multiplier is **100** for every contract we see, and
exposures undercount around such corporate actions (not flagged; the run stat is the only
trace). Cash-settled index options (SPX, NDX, RUT) are outside the universe (ADR 0013) and
their PM-settled weekly roots (SPXW) would be non-standard anyway: index positioning shows
through the ETFs (SPY, QQQ, IWM). ETFs are treated exactly like stocks.

**Expiries (Proposed).** Every stored expiry with `dte >= 1`, where `dte = expiry - session`
in calendar days. `dte = 0` contracts expired at the snapshot (the feed still lists them:
71k of 1.52M rows on 2026-10-02) and are excluded from exposures and OI, but their volume
counts (it traded that day). Alternative: the roadmap's 0..60 days. Reason: on 2026-10-02 only
46% of the universe's OI-weighted gamma (feed gamma) sat within 60 days, so a cap moves walls
on names with large LEAPS open interest. The cap stays a parameter (`max_dte`, unset) so a
later version can apply one.

**Next expiry (Proposed).** The first listed expiry with `dte >= 1`, weeklies and dailies
included. Alternative: the first standard monthly. Reason: on names with weeklies the nearest
weekly holds most of the short-dated gamma, and that is what "next expiry" means on a panel.
For a name with monthlies only, both rules agree.

**Quotes.** Two-sided: `bid > 0` and `ask > bid` (crossed and locked quotes are not
two-sided; none were crossed on 2026-10-02, 314k had a zero bid). `mid = (bid + ask) / 2`.
A **smile quote** is two-sided with `(ask - bid) / mid <= max_spread_pct` (0.35, as `iv30`).
Null `open_interest` or `volume` counts as 0 (as `put_wing` does).

**Per-contract IV (Proposed).** Per expiry, with `t = dte / 365`, `r = curve(t)`,
`F = S0 e^{(r - q) t}`:

1. Invert the mid of every smile quote with `quant.implied_vol` (status `OK` only).
2. Build the expiry's smile by strike from the out-of-the-money leg: the put's IV for
   `K < F`, the call's for `K >= F`; if that leg has no IV, the other leg's.
3. Every contract of the expiry (smile quote or not, any OI) gets `iv(K)`: its own strike's
   smile value, else linear interpolation in strike between the neighbouring smile strikes,
   flat beyond the outermost ones.
4. An expiry with no smile point has no IV: its contracts are **unpriced** (no Greeks),
   counted in `n_unpriced` and in `unpriced_oi_share`.

Alternative: price only contracts with their own two-sided quote. Reason: open interest sits
on strikes with a zero bid (far OTM, far dated), and dropping them biases walls toward liquid
strikes. The feed's own `gamma` is never used as a fallback (unknown model; ADR 0014).

**Greeks.** `quant.black_scholes.greeks(S0, K, t, r, q, iv, is_call)`: `delta` (calls 0..1,
puts -1..0) and `gamma` (per $1 of spot, per share, >= 0).

**Status and nulls.** Each group has one status label, never null; the first failing step
wins. A null value is UNKNOWN, never zero; a ratio with a zero denominator is null, never 0 or
infinity.

**Point in time (ADR 0007).** A row for session S reads only the S partitions of the chain
tables (the latest run known at `as_of`, snapshot rule), the curve S sees, `div_yield@v1`,
`earnings@v1` and `price_stats@v2` rows for S, and (window groups) its own inputs for S and
the sessions before it. The chain snapshot's `ts` is after the close and often the next UTC
day; the row is still S's. OI is not shifted to S-1's partition: the feed's OI on S's
snapshot is what was knowable on S. A re-run of S's chains is picked up by re-running the
rollups for S; `knowledge_ts` and `run_id` are the rollup run's, as for every group.

**Unaffected by design.** Early-close sessions (time is calendar days to expiry, so no
change); holiday-shifted expiries (taken from the listed dates). A stale chain (`STALE_DATA`)
or a failed fetch stores no quotes, so the groups say NO_CHAIN.

## P1: dealer sign convention

**Proposed.** Dealers are assumed **long calls and short puts**, i.e. customers are net
short calls (overwriting) and net long puts (protection). So call gamma counts **+** and put
gamma **-** in every gamma exposure. Alternative: the reverse (customers long calls, short
puts; call gamma -), which describes speculative call buying better on some single names.
Reason: it is the convention every published GEX series uses, so our numbers compare with
the panel's; the assumption is stated in every gamma feature's description. Note: the OP0
brief phrased the assumption as "customers long calls / short puts", which is the reverse;
the roadmap row ("calls +, puts -, dealers long calls") matches this proposal.

Delta exposure carries **no** positioning assumption: it is the open interest's own dollar
delta, calls positive and puts negative.

## P2: dollar scaling

**Proposed.** Gamma exposure in **US dollars of delta change per 1% move in spot**, delta
exposure in **US dollars of delta** (share-equivalents times spot):

```
GEX_i = sign_i x gamma_i x OI_i x 100 x S0^2 x 0.01      sign = +1 call, -1 put
DEX_i = delta_i x OI_i x 100 x S0
```

`gamma x OI x 100` is the shares of delta change per $1 move; times `0.01 S0` for a 1% move,
times `S0` for dollars. Alternative: per $1 move (drop `S0 x 0.01`), or shares instead of
dollars. Reason: per 1% in dollars compares across names and prices (a $10 and a $1,000
stock), and is the panel's convention. Stored as `float32` in `usd` (about 7 significant
digits; SPY's per-1% gross is around $3e10).

## OP1: `gex@v1` (kind `chain`)

Inputs as in [Shared rules](#shared-rules-every-op-group). Params `rollups.toml ["gex@v1"]`:
`max_dte` (unset: all), `max_spread_pct` (0.35), `flip_range` (0.30), `flip_step` (0.01),
`partial_share` (0.20).

Per contract `i` (priced, `dte >= 1`): `GEX_i`, `DEX_i` as in P2. By strike `k`:
`G_k = sum GEX_i`, `D_k = sum DEX_i` over both rights and every included expiry; `C_k`, `P_k`
the call-only and put-only parts of `G_k`. By expiry `e`: `G_e`, `D_e` likewise.

| Feature | Kind | Type | Unit | Valid | Formula | Null when |
|---|---|---|---|---|---|---|
| `gex_status` | label | str | category | OK, PARTIAL, NO_SPOT, NO_CHAIN, NO_OI, NO_GREEKS | first failing step: no spot; no contract with `dte >= 1`; total OI 0; no priced contract. PARTIAL: values computed but `unpriced_oi_share > partial_share` | never |
| `spot` | chain | float32 | usd_per_share | >= 0 | `S0` | NO_SPOT |
| `gex_call` | chain | float32 | usd | >= 0 | `sum GEX_i`, calls | status not OK / PARTIAL |
| `gex_put` | chain | float32 | usd | <= 0 | `sum GEX_i`, puts | same |
| `gex_net` | chain | float32 | usd | any | `gex_call + gex_put` | same |
| `dex_call` | chain | float32 | usd | >= 0 | `sum DEX_i`, calls | same |
| `dex_put` | chain | float32 | usd | <= 0 | `sum DEX_i`, puts | same |
| `dex_net` | chain | float32 | usd | any | `dex_call + dex_put` | same |
| `call_wall` | chain | float32 | usd_per_share | >= 0 | strike with the largest `C_k` | same, or every `C_k` is 0 |
| `put_wall` | chain | float32 | usd_per_share | >= 0 | strike with the largest `abs(P_k)` | same, or every `P_k` is 0 |
| `key_gamma_strike` | chain | float32 | usd_per_share | >= 0 | strike with the largest `abs(G_k)` | same |
| `key_delta_strike` | chain | float32 | usd_per_share | >= 0 | strike with the largest `abs(D_k)` | same |
| `gamma_flip` | chain | float32 | usd_per_share | >= 0 | zero-gamma level nearest `S0` (below) | same, or no sign change within `S0 x (1 +- flip_range)` |
| `next_expiry` | chain | date | date | | first expiry with `dte >= 1` | NO_SPOT, NO_CHAIN |
| `gex_next_exp` | chain | float32 | usd | any | `G_e` at `next_expiry` | status not OK / PARTIAL, or the next expiry is unpriced |
| `dex_next_exp` | chain | float32 | usd | any | `D_e` at `next_expiry` | same |
| `top_gamma_expiry` | chain | date | date | | expiry with the largest `sum abs(GEX_i)` (gross) | status not OK / PARTIAL |
| `top_delta_expiry` | chain | date | date | | expiry with the largest `sum abs(DEX_i)` (gross) | same |
| `n_expiries` | chain | int | count | >= 0 | expiries with `dte >= 1` (within `max_dte`) | NO_SPOT, NO_CHAIN |
| `n_unpriced` | chain | int | count | >= 0 | included contracts without an IV (P-IV step 4) | NO_SPOT, NO_CHAIN |
| `unpriced_oi_share` | chain | float32 | decimal | 0 .. 1 | OI of unpriced contracts / total included OI | NO_SPOT, NO_CHAIN, NO_OI |

**Ties (Proposed)** for every "largest" above: the strike nearest `S0`, then the lower
strike; for expiries, the earlier. A strike is a listed strike, never interpolated.

**Walls (Proposed).** By gamma exposure, any strike (not restricted to above / below spot).
Alternatives: by open interest; or call wall restricted to strikes above `S0`, put wall
below. Reason: gamma weights OI by moneyness and time, which is what makes a strike "hold";
OI alone is dominated by far-dated LEAPS. A side restriction makes a wall jump to another
strike the day spot crosses it, which hides exactly the event a trader watches. In practice
the gamma-weighted call wall sits at or above spot and the put wall at or below.

**Hedge Wall = `gamma_flip` (Proposed).** The spot level where the dealer book's net gamma
changes sign: for `x` on the grid `S0 x (1 - flip_range) .. S0 x (1 + flip_range)` in steps
of `flip_step x S0`, recompute `net(x) = sum sign_i x gamma_i(x) x OI_i x 100 x x^2 x 0.01`
with each contract's IV, `t`, `r`, `q` held fixed; find every grid interval where `net`
changes sign, take the one nearest `S0`, and interpolate linearly inside it. Alternatives: the
strike where cumulative `G_k` (strikes ascending) crosses zero (no re-pricing, cheaper, but a
strike-ladder artefact); or a vendor's proprietary "hedge wall", which is not published.
Reason: the re-priced zero-gamma level is the documented, reproducible quantity; above it
dealer hedging damps moves, below it amplifies them (under P1). Implementation note: the grid
needs gamma only, so a pdf-only `quant` gamma (no CDF) keeps it cheap (measured 1.7 s for
61 levels x 0.7M contracts; the full `greeks` call is about 1 s per level).

**Options Impact (Proposed), expression feature.**
`options_impact = if(price_stats.adv_usd_20d > 0, (gex.gex_call - gex.gex_put) / price_stats.adv_usd_20d, null)`,
unit `ratio`, range `>= 0`: gross dollar gamma per 1% move as a share of the stock's
20-session average dollar volume, i.e. how much of a normal day's trading dealer re-hedging of
a 1% move would be if all gamma hedged the same way. Alternative: one session's volume
(noisier), or net instead of gross gamma (cancels to near zero on balanced books). The panel's
own "Options Impact" is proprietary; this is our documented proxy, not a replica.

**Worked example.** `S0 = 100`, `r = 0.04`, `q = 0`, two expiries (values from
`quant.black_scholes.greeks`, rounded):

| Contract | IV | OI | gamma | delta | GEX ($/1%) | DEX ($) |
|---|---|---|---|---|---|---|
| 30d C95 | 0.31 | 500 | 0.03614 | 0.7449 | 180,685 | 3,724,577 |
| 30d C100 | 0.30 | 2,000 | 0.04623 | 0.5324 | 924,638 | 10,647,403 |
| 30d C105 | 0.28 | 3,000 | 0.04326 | 0.2992 | 1,297,831 | 8,975,962 |
| 30d P95 | 0.33 | 4,000 | 0.03470 | -0.2662 | -1,388,130 | -10,649,653 |
| 30d P100 | 0.30 | 1,500 | 0.04623 | -0.4676 | -693,479 | -7,014,448 |
| 30d P105 | 0.29 | 200 | 0.04222 | -0.6935 | -84,448 | -1,386,951 |
| 3d C100 | 0.25 | 1,000 | 0.17596 | 0.5103 | 1,759,588 | 5,103,067 |
| 3d P100 | 0.25 | 1,200 | 0.17596 | -0.4897 | -2,111,505 | -5,876,319 |

(`GEX` of 30d C100: `0.04623 x 2000 x 100 x 100^2 x 0.01 = 924,600`, 924,638 unrounded.)

- `gex_call = 4,162,742`, `gex_put = -4,277,562`, `gex_net = -114,820`;
  `dex_call = 28,451,009`, `dex_put = -24,927,372`, `dex_net = 3,523,637`.
- By strike, `G_k`: 95: -1,207,445; 100: -120,758; 105: 1,213,383. `key_gamma_strike = 105`
  (1,213,383 beats 1,207,445). `D_k`: 95: -6,925,076; 100: 2,859,703; 105: 7,589,010, so
  `key_delta_strike = 105`.
- `C_k` largest at 100 (2,684,226), `call_wall = 100`; `abs(P_k)` largest at 100 (2,804,984),
  `put_wall = 100`.
- `net(x)` at 100: -114,820; at 101: 71,952. `gamma_flip = 100 + 114,820 / (114,820 + 71,952)
  = 100.61`.
- `next_expiry` = the 3-day expiry: `gex_next_exp = -351,918`, `dex_next_exp = -773,252`.
  Gross gamma: 3d 3,871,093, 30d 4,569,212, so `top_gamma_expiry` = 30d; gross delta 3d
  10,979,387 vs 30d 42,398,994, `top_delta_expiry` = 30d.
- With `adv_usd_20d = 500,000,000`: `options_impact = 8,440,304 / 5e8 = 0.0169`.

## OP2: `chain_flow@v1` (kind `chain`) and the ratios

Inputs: the session's `chains/option_quotes` only (no spot, no pricing). Volume counts every
stored contract including `dte = 0`; OI counts `dte >= 1` (see [Shared rules](#shared-rules-every-op-group)).
"Next expiry" is the same rule as `gex.next_expiry`.

| Feature | Kind | Type | Unit | Valid | Formula | Null when |
|---|---|---|---|---|---|---|
| `flow_status` | label | str | category | OK, NO_CHAIN | NO_CHAIN: no quotes for the underlying on the session | never |
| `call_volume` | chain | int | count | >= 0 | sum of call `volume`, every expiry | NO_CHAIN |
| `put_volume` | chain | int | count | >= 0 | sum of put `volume`, every expiry | NO_CHAIN |
| `call_oi` | chain | int | count | >= 0 | sum of call `open_interest`, `dte >= 1` | NO_CHAIN |
| `put_oi` | chain | int | count | >= 0 | sum of put `open_interest`, `dte >= 1` | NO_CHAIN |
| `next_exp_call_volume` | chain | int | count | >= 0 | call volume at the next expiry | NO_CHAIN, or no expiry with `dte >= 1` |
| `next_exp_put_volume` | chain | int | count | >= 0 | put volume at the next expiry | same |

`chain_oi` / `chain_volume` in `option_liquidity@v1` stay as they are (standard-series totals
for the liquidity tiers, with `dte = 0` OI included); these columns split by right and follow
the positioning rules.

**Ratios (Proposed), expression features** in `config/site/features/positioning.toml`, all
**put over call** in absolute terms (above 1 = put-heavy), unit `ratio`, range `>= 0`, null
when the denominator is 0 or either side is null (never 0, never infinity):

| Feature | Expression |
|---|---|
| `put_call_oi_ratio` | `if(chain_flow.call_oi > 0, chain_flow.put_oi / chain_flow.call_oi, null)` |
| `volume_ratio` | `if(chain_flow.call_volume > 0, chain_flow.put_volume / chain_flow.call_volume, null)` |
| `gamma_ratio` | `if(gex.gex_call > 0, abs(gex.gex_put) / gex.gex_call, null)` |
| `delta_ratio` | `if(gex.dex_call > 0, abs(gex.dex_put) / gex.dex_call, null)` |

Alternative for `volume_ratio`: total option volume / stock volume ([Q4](#open-questions-for-the-owner)).
Worked example (OP1 numbers): `gamma_ratio = 4,277,562 / 4,162,742 = 1.028`,
`delta_ratio = 24,927,372 / 28,451,009 = 0.876`. A name with 1,200 put and 0 call volume has a
null `volume_ratio`, not infinity.

## OP3: `skew@v1` (kind `chain`) and `skew_history@v1` (kind `window`)

**Definition (Proposed).** Normalised 25-delta risk reversal:
`skew = (iv_25p - iv_25c) / iv_atm`, at a constant 30-day maturity. Positive = puts richer
than calls. Alternative: the raw difference `iv_25p - iv_25c` in vol (decimal). Reason:
normalising by ATM vol makes a 5-point skew on a 20-vol name and on an 80-vol name
comparable across the universe, and keeps the rank from mostly tracking the vol level. The
raw difference stays available as the expression `skew_rr25 = skew.iv_25p - skew.iv_25c`.

Per expiry (priced as in [Shared rules](#shared-rules-every-op-group), smile quotes only, our
delta at the contract's own IV):

- `iv_25p`: puts with our delta, the two whose delta brackets -0.25, IV linear in delta.
- `iv_25c`: calls likewise around +0.25.
- `iv_atm`: the mean of the call IV interpolated at delta 0.50 and the put IV at -0.50.
- No extrapolation: no bracketing pair on a side means no value for that expiry.

Delta is the spot delta of BSM (with `e^{-qt}`), not a forward or premium-adjusted delta.

**Maturity.** `skew`, `iv_25p`, `iv_25c`, `iv_atm`: the two expiries bracketing 30 days among
7..90 days out (standard monthlies first when they bracket, else any listed expiry), as
`iv30@v1` chooses them; each of the three vols interpolated linearly in total variance
`sigma^2 t` to 30 days, then `skew` from the interpolated vols. One usable expiry: its values
unchanged, status SINGLE_EXPIRY. `ne_skew`: the same per-expiry formula at the next expiry
(the `gex` rule), no interpolation (**Proposed**; alternative: the first expiry at least 7
days out, less noisy, but not what "next expiry" means elsewhere). Very short expiries have
25-delta strikes close to the money and noisy vols; `ne_dte` lets a screen ignore them.

| Feature | Kind | Type | Unit | Valid | Null when |
|---|---|---|---|---|---|
| `skew_status` | label | str | category | OK, SINGLE_EXPIRY, NO_SPOT, NO_CHAIN, NO_EXPIRY, NO_ATM, NO_WING | never |
| `skew` | chain | float32 | ratio | -1 .. 2 | status not OK / SINGLE_EXPIRY |
| `iv_25p` | chain | float32 | decimal | 0 .. 5 | same |
| `iv_25c` | chain | float32 | decimal | 0 .. 5 | same |
| `iv_atm` | chain | float32 | decimal | 0 .. 5 | same |
| `ne_skew` | chain | float32 | ratio | -1 .. 2 | no next expiry, or it has no ATM or no bracketing 25-delta put and call |
| `ne_dte` | chain | int | days | >= 1 | no next expiry |

Statuses (first failing step): NO_SPOT, NO_CHAIN, NO_EXPIRY (none 7..90 days), NO_ATM (no
expiry with an ATM vol), NO_WING (ATM, but 25 delta not bracketed on a side).

**Worked example (one expiry).** Puts: delta -0.20 at IV 0.34, -0.30 at 0.31, so
`iv_25p = 0.325`. Calls: 0.30 at 0.27, 0.20 at 0.26, so `iv_25c = 0.265`. ATM: calls 0.55 at
0.285 and 0.45 at 0.280 give 0.2825; puts -0.45 at 0.290 and -0.55 at 0.300 give 0.295;
`iv_atm = 0.28875`. `skew = (0.325 - 0.265) / 0.28875 = 0.208`. Term step for `iv_25p` with
0.325 at 21 days and 0.315 at 49 days: `w = 0.325^2 x 21/365 = 0.006077`,
`0.315^2 x 49/365 = 0.013321`; at 30 days `w = 0.006077 + (0.013321 - 0.006077) x 9/28 =
0.008405`; `iv_25p(30d) = sqrt(0.008405 x 365/30) = 0.3198`.

**`skew_history@v1`** (window; input `skew@v1` over 252 sessions), exactly the `iv_history`
pattern:

| Feature | Kind | Type | Unit | Valid | Formula | Null when |
|---|---|---|---|---|---|---|
| `skew_rank_252d` | window | float32 | decimal | 0 .. 1 | `(skew - min) / (max - min)` over the last 252 sessions' skews, today included | `skew_rank_status` UNKNOWN, no skew today, or every value equal |
| `skew_percentile_252d` | window | float32 | decimal | 0 .. 1 | share of the window's earlier skews strictly below today's | UNKNOWN, no skew today, or no earlier value |
| `history_days` | window | int | sessions | 0 .. 252 | sessions in the window with a skew | never |
| `skew_rank_status` | label | str | category | UNKNOWN, PROVISIONAL, FULL | UNKNOWN below 60 sessions with a skew, PROVISIONAL below 252, FULL from 252 | never |

**Proposed:** the same 60 / 252 thresholds as IV rank (owner decision for `iv_history`), on
the 30-day `skew` (not `ne_skew`, whose maturity changes daily). Example: 70 sessions with a
skew, min 0.10, max 0.30, today 0.25: rank 0.75, PROVISIONAL. "Backfill" means recomputing
`skew@v1` for every stored chain session; with chains stored from 2026-10-02 the rank is
UNKNOWN until about the end of 2026 and FULL around October 2027. No outside source has
per-name skew history for free.

## OP4: `implied_move@v1` (kind `chain`)

Inputs: the shared chain inputs plus `earnings@v1` for the session. Params: `max_dte` (60),
`target_dte` (30), `max_spread_pct` (0.35).

**Expiry (Proposed).** If `next_earnings_date` is known and the first expiry covering it is
within `max_dte`: that expiry (`move_basis = EARNINGS`). An expiry covers a report on date D
if it is after D, or on D when `earnings_time = pre`; `post` or `unknown` needs an expiry
after D. Otherwise the listed expiry nearest `target_dte` among 7..`max_dte` days (ties: the
earlier; `move_basis = TERM`). Alternative: always the next expiry. Reason: the panel number
is read as "what the market prices into the next event", and the earnings straddle is the
standard way to read that.

**Formula (Proposed).** At that expiry, the straddle mid `C(K) + P(K)` at the two listed
strikes bracketing `S0` (both legs two-sided with spread <= `max_spread_pct`), interpolated
linearly in strike to `S0` (one usable strike: its straddle). Then
`implied_move = straddle / S0`. No 0.85 factor. Reason: the ATM straddle already prices the
expected absolute move (`E|dS| = sigma sqrt(t) S sqrt(2/pi)`, about 0.8 `sigma sqrt(t) S`,
which equals the ATM straddle to first order); the 0.85 rule is a trader's heuristic with no
fixed basis. A one-standard-deviation move, if wanted, is the expression
`implied_move x 1.2533` (`sqrt(pi/2)`).

| Feature | Kind | Type | Unit | Valid | Null when |
|---|---|---|---|---|---|
| `move_status` | label | str | category | OK, NO_SPOT, NO_CHAIN, NO_EXPIRY, NO_QUOTES, WIDE_SPREADS | never |
| `implied_move` | chain | float32 | decimal | 0 .. 2 | status not OK |
| `straddle_mid` | chain | float32 | usd_per_share | >= 0 | status not OK |
| `move_expiry` | chain | date | date | | NO_SPOT, NO_CHAIN, NO_EXPIRY |
| `move_dte` | chain | int | days | >= 1 | same |
| `move_basis` | label | str | category | EARNINGS, TERM | same |

Worked example: `S0 = 101`; strike 100: call 3.60 + put 2.50 = 6.10; strike 105: 1.40 + 5.30
= 6.70; at 101: `6.10 + (6.70 - 6.10) x 1/5 = 6.22`; `implied_move = 6.22 / 101 = 0.0616`
(a 6.2% expected absolute move to that expiry).

## prev_close

**Proposed:** `price_moves@v2` adds `prev_close` (window, float32, usd_per_share, `>= 0`):
the close of the previous exchange session (`core.time.calendar`), split-adjusted as of the
session (a split between the two sessions divides it by the ratio, as `price_stats` adjusts).
Null when the previous session has no bar. `one_day_move` is unchanged; `ret_1d =
price_stats.close / price_moves.prev_close - 1` becomes an expression feature. Alternatives:
(a) `price_stats@v3`, as the roadmap row says: re-versions the group that `dividends@v2`,
`fundamentals@v2` and many expressions read, for one column; (b) the feed's
`underlying_quotes.prev_close`: measured on 2026-10-02 it equalled the previous session's bar
close for only 76% of names (the after-close snapshot had already rolled it to the session's
own close for many), and it exists only for optionable names. `price_moves@v1` is small and
has no dependents, so a v2 is cheap; v1 is retired with `retire-features` after the backfill.

## Compute cost and footprint

Per night, about 4.2k rows per group, each table well under 1 MB. Compute, estimated from
timings on this machine (2026-10-04; to be re-measured on the real store):

| Group | Work per session | Estimate |
|---|---|---|
| `gex@v1` | IV inversion of the smile quotes (about 1M two-sided contracts with `dte >= 1`), Greeks for about 1.45M, flip grid on OI > 0 contracts | about 20 to 30 s (synthetic: 16 s to invert 0.86M, 1.2 s for Greeks, 1.7 s for a 61-level pdf-only flip grid on 0.7M) |
| `chain_flow@v1` | group sums | under 1 s |
| `skew@v1` | inversion of 2 to 3 expiries per name | a few seconds |
| `skew_history@v1` | window over its own input | like `iv_history`, seconds |
| `implied_move@v1` | mids only, no inversion | under 1 s |

Each group inverts on its own (groups are pure and do not share intermediates); a stored
per-contract Greeks table would remove the duplication at about 1.5M rows a night and is not
proposed for v1. After OP1 and OP3 land, re-measure in [nightly-footprint.md](nightly-footprint.md):
the rollups step's duration per group, `gex@v1` peak memory on a full chain partition, rows
and Parquet size per new table, and the backfill time per stored chain session.

## Implementation notes (for OP1 to OP4, not decisions)

- `src/algotrade/features/rollups/` holds 10 modules, the layout cap: split it by kind before
  the first OP group (`add-responsibility`, `layout.toml`).
- The per-contract IV fill and Greeks (Shared rules) are one new responsibility used by `gex`,
  `skew` and later `put_wing`'s `our_deltas`: one owner module, an `ownership.toml` entry, no
  copies (`make dupes`). The pdf-only gamma belongs in `quant/` (architect review).
- New tables need `[[table]]` entries; expression features go in
  `config/site/features/positioning.toml`; params in `config/site/rollups.toml`.

## Validation plan

1. **Golden chains (unit).** The OP1, OP3 and OP4 worked examples above as fixtures with the
   expected values (relative tolerance 1e-6 on our maths; the rounded table values are for
   reading). Plus edge chains: calls only, puts only, every OI 0, one expiry, `dte = 0`
   only, an expiry with no smile quote, a strike with a zero bid and large OI, a crossed
   quote.
2. **Properties (`tests/property`, hypothesis).** `gex_call >= 0 >= gex_put`,
   `dex_call >= 0 >= dex_put`, nets are the sums; `sum_k G_k = sum_e G_e = gex_net` (and for
   delta); scaling all OI by `c` scales every exposure by `c` and leaves walls, key strikes,
   flip and expiries unchanged; row order never changes output; walls and key strikes are
   listed strikes; `gamma_flip` lies inside the grid and `net` changes sign around it;
   adding a `dte = 0` contract changes volume only; a call and a put at the same strike and
   IV have equal gamma; ratios are null exactly when their denominator is 0; ranks are in
   0..1 and null when UNKNOWN; `implied_move` is monotone in both legs' mids.
3. **Against the feed (reconciliation, recorded chain).** Our IV and gamma vs the feed's
   `iv` and `gamma` on liquid near-ATM contracts (expect agreement within a few percent;
   report the distribution); `gex_net` from our gamma vs from the feed's gamma (sign agrees
   on liquid names); `chain_flow` totals vs `option_liquidity.chain_oi` / `chain_volume`
   (identical for volume; OI differs only by `dte = 0`).
4. **Against IBKR (LV track, `tasks/verification/checks.py`).** For the verification sample:
   IB's option call / put volume and open interest per underlying (generic ticks 100 and 101
   through the existing `reqMktData`; not yet confirmed on delayed data) vs `chain_flow`
   (WARN, not FAIL: IB counts adjusted series we drop); IB's model IV and gamma for a few
   ATM contracts per name vs ours. No IB call is added; new tick types are noted in ADR 0026's
   allowlist review.
5. **Panel spot check (manual, once).** A handful of names against the third-party panel on
   the same date. Expect walls and key strikes to agree on liquid names and dollar figures to
   differ by convention; record the comparison in the OP1 PR, not as a test.
6. **Feature quality (FS7).** The valid ranges above feed the nightly null-rate and range
   report.

## Open questions for the owner

1. **Sign convention (P1).** Confirm dealers long calls / short puts (call gamma +). The OP0
   brief's wording said the reverse.
2. **Hedge Wall and Options Impact.** Is "Hedge Wall" the zero-gamma level (`gamma_flip`)?
   Is our Options Impact proxy (gross gamma / 20-day dollar volume) acceptable, given the
   panel's is proprietary?
3. **Expiry window.** All stored expiries (proposed) or the roadmap's 60 days?
4. **Volume Ratio.** Put volume / call volume (proposed) or option volume / stock volume?
5. **Skew.** Normalised by ATM vol (proposed) or the raw 25-delta difference, as the basis of
   Skew Rank?
6. **Panel count.** The brief lists 38 fields; the roadmap says 40. Which two are missing?
