# Instruments and the universe

Decision records: [ADR 0009](../adr/0009-generic-instrument-model.md),
[ADR 0013](../adr/0013-universe.md).

## Generic instrument model

Every tradable or observable thing is an **instrument** with a stable `instrument_id`.
Data is keyed by `instrument_id`, never by ticker string.

| Field | Notes |
|---|---|
| `instrument_id` | Internal, stable, never reused |
| `asset_class` | `equity`, `etf`, `index`, `option`, `future`, `future_option`, (`fx`, `crypto` reserved) |
| `symbol`, `name`, `exchange`, `currency` | Symbol history is kept separately (renames, reuse) |
| `parent_id` | Option → underlying; future → root; future option → future |
| `multiplier` | 1 for stocks, 100 for US equity options, 50 for ES, … **All P&L uses it.** |
| `expiry`, `strike`, `right` | Derivatives only |
| `contract_month`, `root` | Futures only (for example root `ES`, month `2026-12`) |
| `calendar` | Exchange calendar id. Defines sessions and `session_date`. |
| `tick_size` | Minimum price increment |
| `etf_flags` | `is_etf`, `is_leveraged`, `is_inverse`, `leverage` (for example `3.0`, `-1.0`), `tracks` (underlying index) |
| `valid_from`, `valid_to` | Reference rows are versioned history (delistings, renames) |

### Why this makes futures (and options) "just more data"

- Futures contracts are instruments with `parent_id → root`. Continuous series (for example
  back-adjusted `ES`) are a **derived dataset** with the roll rule recorded in its metadata,
  never mixed with the raw contract data.
- Exchange calendars give each bar a `session_date`. ES trading at 23:00 UTC belongs to the
  next session; the engine works in sessions, not calendar days.
- `multiplier` lives on the instrument, so portfolio accounting stays one formula:
  `value = qty × price × multiplier`. (Today's `Portfolio` assumes multiplier 1; it must
  read the instrument multiplier before any options or futures backtest. This is tracked
  in the roadmap.)
- Roll and expiry dates are **events**, so strategies see them through features, not magic.

## The universe

Saved as a dated snapshot every day (`normalized/universe/date=…`), so backtests use the
universe *as it was*, which avoids survivorship bias.

| Segment | Source | Notes |
|---|---|---|
| S&P 500 constituents | SPY daily holdings file (State Street) | Membership changes become `index_add` / `index_remove` events |
| All Nasdaq-listed stocks | Nasdaq Trader `nasdaqlisted.txt` | Exclude test issues (`Test Issue = Y`) |
| All ETFs (any exchange) | `nasdaqlisted.txt` + `otherlisted.txt` (`ETF = Y`) | Most ETFs list on NYSE Arca, so they come from `otherlisted.txt` |
| Leveraged and inverse ETFs | Subset of ETFs, flagged | See below |
| Optionable flag | Nasdaq Trader `options.txt` (underlying symbols) | About 4.2k underlyings as of 2026-10 |
| Futures (later) | Curated root list (ES, NQ, RTY, CL, GC, ZN, …) | Added as roots; contracts come from the vendor |

### Flagging leveraged and inverse ETFs

There is no free official flag. Each ETF's `leverage` (signed: negative = inverse) and
`leverage_source` are resolved in this order (`tasks/reference/classify.py`, rules in
`config/site/universe.toml`, all patterns case-insensitive on the security name):

1. **Curated override** (`config/site/overrides/leveraged_etfs.csv`: symbol, leverage, tracks)
   wins → `override`. Use it when the name is wrong or silent (e.g. UVXY is 1.5x and SVXY
   -0.5x although "ProShares Ultra" / "ProShares Short" say 2 and -1).
2. **Leverage stated in the name** → `name_parsed` (KNOWN, not reviewed):
   - fund-family conventions (`leverage_conventions`, first match wins): "ProShares Ultra X"
     = 2, "ProShares UltraShort X" = -2, "(ProShares) UltraPro X" = 3, "(ProShares) UltraPro
     Short X" = -3, "ProShares Short X" = -1;
   - a stated multiple (`leverage_patterns`): a number with x next to a direction word or
     "Daily" ("Bull 3X", "2X Short", "2x Daily", "Daily Target 2X"), a name that starts with
     one ("2x Bitcoin ETF") or ends "2X ETF", or "N (Inverse) Leveraged" ("-3 Inverse
     Leveraged ETNs"). The sign is negative when the number is, or when the name has an
     `inverse_markers` word (Short, Bear, Inverse) outside the exclusion phrases below.
3. **Exclusions** (`leverage_exclusions`): phrases that use a marker word without meaning
   leverage (short / ultra-short duration, term and maturity bonds, "Short Muni", "Ultra
   Buffer", "PutWrite", "Option Income", "Covered Call", "Premium Income", "Daily Income",
   "Long/Short", "Leveraged Loan") are blanked out. If no leverage marker is left the ETF is
   unleveraged → `name_rule`. A marker that remains ("Inverse VIX Short-Term Futures")
   still needs review.
4. **No marker** (`leverage_markers`: Nx, Ultra, Bull, Bear, Inverse, Short, Leveraged,
   Daily) → unleveraged, `name_rule`.
5. **Anything else** → UNKNOWN (`needs_review`: `is_leveraged`, `is_inverse`, `leverage` all
   null) and listed in the review file. Fails closed.

Non-ETFs are `not_etf` (unleveraged). On the 2026-10-02 listings these rules took the review
file from 958 names to 21 (770 `name_parsed`, 165 excluded, 2 VIX overrides).

Leveraged ETFs reset daily, so long-horizon returns drift away from leverage × index
return (volatility decay). The feature library must expose `leverage` and `is_inverse` so
strategies and screeners can account for it.


## Universe build (implemented, phase 1.2)

`algotrade-ingest universe-build [--date D] [--review-out candidates.csv]` (and the nightly
job when `config/site/universe.toml` has `source = "nasdaq_trader"`):

1. Fetches `nasdaqlisted`, `otherlisted`, `options` (Nasdaq Trader) and SPY holdings
   (State Street); raw responses are kept for 90 days.
2. Classifies every listing: `COMMON_STOCK` (incl. partnership units), `ADR`, `ETF`, `ETN`,
   `PREFERRED`, `WARRANT`, `UNIT`, `RIGHT`, `NOTE`, from the name, the ACT symbol and the ETF flag.
3. Writes **all** listings to `instruments/reference` with `optionable`, `in_sp500`,
   `first_seen` and leverage flags. Instruments no longer listed stay as `DELISTED` with
   `delisted_on`.
4. Writes the **coverage** (`security_types`, test issues, include/exclude lists in
   `universe.toml`) to `universe`.
5. Writes `events/reference_change` (added, removed, renamed, type / optionable / exchange
   changed) and `events/index_change` (S&P 500 adds and removes). S&P members that match no
   listing make the run PARTIAL.

Leverage: resolved as in "Flagging leveraged and inverse ETFs" above (override → name parsed
→ exclusions → no marker → `needs_review`); the run stats count each `leverage_source`.
`--review-out` writes the ETFs still UNKNOWN (2026-10-02: 21) with an empty `leverage` for
the curator. Curate by checking the issuer's factsheet and adding the row to the overrides file.


## Identifiers and vendor types (implemented, phase 1.5)

When a Massive key is configured, the universe build also reads Massive's ticker list (~13
requests): every row gets `figi` (composite), `share_class_figi` and `cik`, and **Massive's
security type wins over the name rules** (`security_type_source` = `vendor` or `name_rule`;
disagreements are counted in the run stats). Notably, closed-end funds (`FUND`) become `CEF`
and drop out of the default coverage.

`instruments/symbol_history` tracks which symbol each FIGI used and when; a FIGI that comes
back under a new symbol closes the old row and emits `events/reference_change` with
`change = ticker_changed` (e.g. FB -> META).
It keeps **one row per key** (`figi`, `symbol`, `valid_from`): a (FIGI, symbol) listed again
after a run of the same session closed it (a vendor FIGI flipping A -> B -> A, DFAC on
2026-10-02) reopens that row rather than opening a second one, and if two rows still share a
key the build's own decision (the later row) wins.

**Re-runs of a session.** The build's cumulative state (ids, `first_seen`, delistings
carried, `symbol_history`, `id_map`) starts from the latest snapshot **known** when it runs:
an earlier run of the same session if there is one, else the latest earlier session. So a
re-run (the nightly re-building a session built by hand that morning) keeps what the earlier
run recorded, and a listing that only the earlier run saw is carried as `DELISTED`.
`events/reference_change` and `events/index_change` always diff against the **previous
session** (with the session's id upgrades applied), so every run of a session emits the same
rows under the same keys, which the merged event tables absorb. `symbol_history` and
`id_map` are also **merge** tables ([storage.md](storage.md#how-runs-combine)): a run that
holds less can never hide what an earlier run of the session recorded.


## FIGI-based instrument ids (implemented, phase 1.8)

Decision record: [ADR 0018](../adr/0018-figi-instrument-ids.md).

| Instrument | `instrument_id` | Example |
|---|---|---|
| Equity / ETF with a composite FIGI | `EQ:<composite FIGI>` | `EQ:BBG000B9XRY4` (AAPL) |
| Equity / ETF without one (no Massive key, unknown to Massive, golden data) | `EQ:<symbol>` | `EQ:BULL` |
| Option contract | `OPT:<OCC symbol>`; `underlying_id` = the underlying's id | `OPT:SPY261231C00586000` |

- **Stable.** A FIGI id never changes automatically. A ticker change only updates `symbol` in
  the reference (and emits `ticker_changed`). When the previous active listing of a symbol
  held a FIGI id, a build carries the id and FIGI forward when the vendor reports no FIGI
  (`ids_carried`) **and when it reports a different one** (`figi_changes_held`): the vendor's
  FIGI is kept in the reference's `vendor_figi` and the listing goes to the review file. On
  2026-10-02 DFAC's vendor FIGI flipped BBG011DXY5J0 -> BBG0132J6C32 -> BBG011DXY5J0 across
  same-session runs and its id followed; now it keeps `EQ:BBG011DXY5J0`, the id its two years
  of bars are stored under (pinned by a row in `overrides/figi.csv`, so it holds whichever
  run's snapshot a re-build starts from).
- **Shared FIGI.** Two listings with one FIGI (MMED and its when-issued line MMEDV on
  2026-10-02): the listing that already held the id keeps it (else the first symbol); the
  other keeps its symbol id (`figi_conflicts`). Both are in the review file. Only the holder
  has an open `symbol_history` row (before, the last listing won the FIGI's row; such a row is
  closed without a `ticker_changed` event).
- **Review file.** `universe-build --figi-review-out PATH` (default `var/figi_review.csv`; the
  run stats carry the same rows as `figi_review`, counts under `identifiers`) lists every active
  listing under review: `symbol, held_figi, vendor_figi, first_seen, note`. `held_figi` is the
  FIGI its id stands for (blank for a symbol id); `first_seen` is the session the disagreement
  was first seen (`figi_review_since` in the reference, carried while it persists). A row
  disappears when the vendor agrees again or the owner resolves it.
- **Owner resolution.** `config/site/overrides/figi.csv` (`symbol, figi, note`, reviewed via
  PR, loaded and validated by the site settings loader) forces a listing's FIGI; a blank
  `figi` means "no FIGI, symbol id". When the forced FIGI differs from the one the listing
  holds, the build changes its id and records the change in `instruments/id_map` (+ an
  `id_changed` event; `ids_overridden`), so `migrate-ids` moves the stored history. An
  overridden listing is never in the review file.
- **Upgrades.** When a symbol-id instrument gains a FIGI, the universe build writes
  `instruments/id_map` (`old_id`, `new_id`, `symbol`, `effective`, `known_at`; the full map in
  every snapshot; a session's runs merge per (`old_id`, `new_id`), keeping the first
  `known_at`) and an `id_changed` reference-change event; the old id is not reported as
  delisted. Build stats: `identifiers.ids_by_figi`, `ids_by_symbol`, `ids_carried`,
  `ids_upgraded`, `ids_overridden`, `figi_conflicts` (two listings with one FIGI: the holder
  keeps it), `figi_changes_held`, `figi_review` (active listings under review).
- **One resolver.** `SymbolResolver` maps symbol → id from the reference snapshot on or before
  a date (`data.reference.resolver(reader, D)`; before the first snapshot, the earliest one). Active rows
  win a reused ticker. Vendor adapters (Massive bars/splits/dividends, Nasdaq earnings) emit
  `symbol`; jobs resolve ids and count `unresolved` symbols, which keep symbol ids. CLI flags
  (`chains --symbols`), `universe.toml` include/exclude lists and exports stay symbol-based.
- **Migrating stored data.** `algotrade-ingest migrate-ids [--dry-run]` reads the latest
  `instruments/id_map` and rewrites every partition whose latest run holds a mapped id
  (`instrument_id`, `underlying_id`, `parent_id`) as a **new run** with a later
  `knowledge_ts`. Old runs stay readable with `as_of`. Only rows known before the upgrade
  (`known_at`) move, so a symbol id reused later is left alone. A partition that would hold
  both ids is reported, not written. Re-running maps nothing.

Owner steps on an existing store (after the bars backfill finishes):

```bash
algotrade-ingest universe-build            # with ALGOTRADE_MASSIVE_API_KEY set: writes id_map
algotrade-ingest migrate-ids --dry-run     # per-table partition / row counts, writes nothing
algotrade-ingest migrate-ids               # appends the rewritten partitions as new runs
algotrade-ingest migrate-ids --dry-run     # should now report no tables
```

Resolving the FIGI review file:

```bash
algotrade-ingest universe-build                       # writes var/figi_review.csv
# for each row, check the FIGI on openfigi.com; to change a listing's FIGI (or give it a
# symbol id), add `symbol,figi,note` to config/site/overrides/figi.csv in a PR, then:
algotrade-ingest universe-build                       # applies it; id changes go to id_map
algotrade-ingest migrate-ids --dry-run && algotrade-ingest migrate-ids
```
