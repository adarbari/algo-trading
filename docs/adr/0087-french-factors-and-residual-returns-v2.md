# ADR 0087: Fama-French daily factors as published series; residual returns v2

**Status:** proposed (2026-11-01; architect design, owner chose "add French factors"; decisions
3-5 decided by Fable for the owner, pending owner confirmation, `docs/decisions/log.md`). Extends [0048](0048-macro-series-with-vintages.md) (a new
published source and a config form for many-column files) and amends
[0053](0053-edges-hypotheses-outcomes-and-one-harness.md) (EB H11, the factor-neutral outcome)
once decision 3 is confirmed.

## Context
`factor_betas@v1` and `outcomes/instrument/residual_returns@v1` regress on ETF factor proxies
(SPY, IWM - SPY, MTUM - SPY, VLUE - SPY). MTUM and VLUE first trade in 2013-04, so every window
before it is `NO_FACTOR_HISTORY`. `bars/1d` and `forward_returns@v2` now start in 2002, so
the factor-neutral outcome is missing for the 2002-2012 half of the history. That includes the
2008 crisis, where a setup's verdict needs it most.

Kenneth French's data library publishes the long-short research factors daily from 1926: market,
size, value, momentum, profitability, investment, short- and long-term reversal, and industry
portfolios. It is free, built from CRSP, and updated monthly with about a one-month lag (the
2026-11-01 pull reads "created by using the 202609 CRSP database"). Each update rebuilds the
whole history, so past values can change. The files state no terms of use. They carry only
"Copyright <year> Eugene F. Fama and Kenneth R. French".

## Decision
1. **Stored as published macro series, not a new table.** Every relevant daily US file goes into
   `macro/series` (ADR 0048) through the published-file source. The parser is `french_zip`: it
   unzips the file, reads the N-th table by its header line, reads `-99.99` / `-999` as no
   value, and never reads the footer. Values stay in percent, as published.
   - Seven files, one request each per pull: 3-factor (`FF3_*`), 5-factor 2x3 (`FF5_*`; its
     SMB is built differently from the 3-factor one, so both are kept), momentum (`FF_MOM`),
     short- and long-term reversal (`FF_ST_REV`, `FF_LT_REV`), 12 and 49 industries, value and
     equal weighted (`IND12_*`, `IND12EW_*`, `IND49_*`, `IND49EW_*`).
   - The data tenet (owner, 2026-11-01) is to store free, high-quality series before a reader
     exists. Skipped: the other industry cuts (5/10/17/30/38/48, which overlap 12 and 49), the
     portfolio sorts (size x B/M, beta, variance), the monthly and annual files, and the
     international factors. Each is config only when wanted.
2. **Config.** `config/site/macro.toml` is at the file-length cap and `config/site/` is at the
   folder cap. The library's files are declared in `config/site/macro/french.toml`: one
   `[[file]]` block per file (`prefix`, `url`, `parser`, `columns`, `section`) over shared
   `[defaults]`. The loader expands each block into ordinary `MacroSeries`, with keys unique
   across both files. Moving `macro.toml` into the folder is a follow-up.
3. **Point in time.** `pit = "lag"`, `revised = true`, `release_lag_days = 70`,
   `refetch_days = 28`. The 70 days are about five weeks to post, plus the worst case of an
   observation on the 1st, which errs late.
   - A value first seen is dated observation + 70 days (`lagged`).
   - A later pull that changes a value stores a new vintage dated that run's session, never
     earlier (ADR 0048).
   - `knowledge_ts` is the pull time.
   - Known limit, disclosed: the library keeps no old vintages. Before 2026-11 we hold today's
     revised values, backdated by the lag rule, so the data available on a 2005 session looked
     slightly different.
4. **Licence: `personal`** (decided by Fable for the owner, pending owner confirmation). No
   terms are stated, the factors are CRSP-derived (CRSP's agreements restrict derived products
   for sale), and the Shiller CAPE file set the precedent. The terms text records it:
   one pull a month, never redistributed, cite Fama and French. Under ADR 0069, anything
   derived from these series inherits `personal`. The alternative is `open`, on the grounds that
   the data is freely posted and widely cited. Loosening it later is not a config flip: ADR 0069
   decision 3 gates by the stricter licence, so the v2 verdicts must be scored again. Owner
   action: ask kfrench@dartmouth.edu whether the daily files may be used as regression inputs on
   a paid US ideas site. The site would serve only our own betas and residuals, never the
   series, with attribution to Fama/French and CRSP. A yes makes the series `open`.
5. **Residual returns: French factors throughout, as v2** (option (ii), decided by Fable for the
   owner, pending owner confirmation; this PR does not build it). v1 stays unchanged as the open,
   published basis. Two options:
   - **(i) Splice: rejected.** French factors before 2013-05, ETFs after. The ETF factors are
     long-only spreads; SMB, HML and Mom are long-short portfolios. Betas on the two differ in
     size and meaning, so a seam would be a structural break in the label. It would corrupt
     decile spreads and frozen-period comparisons across 2013.
   - **(ii) Recommended:** `factor_betas@v2` and `outcomes/instrument/residual_returns@v2` beside
     v1, which stay unchanged.
     - The betas are a feature at S: an OLS on excess returns (less `FF3_RF`) against market,
       size, value and momentum, over the last 252 sessions whose factor vintage is on or before
       S. Live, that window ends about 48 sessions before S. Betas move slowly, and history uses
       the same rule as live.
     - A v2 residual row is a label. It is written only once a factor vintage covers its window
       end; until then it is pending and filled by a later run. Its `knowledge_ts` is the later
       of the window close and that vintage date. This amends 0053's rule that `knowledge_ts` is
       the window close, for v2 only (a 0053 amendment, as `option_pnl` did). Disclosed: a v2
       row can become known up to about 70 days after its window closes, and the forward paper
       record keeps settling on v1 until the licence allows v2.

## Consequences
- 2002-2012 residuals become measurable after the v2 PR and its backfill (`factor_betas@v2`,
  then `residual_returns@v2`, run detached).
- About 3.5 M first rows enter `macro/series`. The table is clustered by `instrument_id`, and
  local reads scoped to ids prune row groups by their footer stats, so the research series do
  not slow the regime reads (measured in the PR). `check_macro` checks the research series only
  against their own staleness, on the nights they are fetched, and outside the regime series'
  stale share.
- If the library re-estimates its whole history every month, each changed value is a new
  vintage row. The growth is measured over the first two pulls.
- A v2 consumer must divide the percent values by 100.
- Any edge scored on v2 residuals is `personal` until decision 4 says otherwise.
- Real vintages accrue from 2026-11 (one pull a month), so the disclosure that history uses revised values covers less of the history over time.
