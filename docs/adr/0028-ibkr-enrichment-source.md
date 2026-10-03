# ADR 0028: IBKR as an enrichment source (read-only, personal licence, labelled fallbacks)

**Status:** accepted (2026-10-03, owner-approved: IV rank uses IBKR's IV history where
available, ours as the fallback, always labelled with its source; IBKR strictly read-only).
Extends [0026](0026-live-verification-ibkr.md) (the read-only facade, session sources),
[0023](0023-feature-store.md) (feature metadata, expression features) and
[0012](0012-data-vendors.md) (IBKR as a secondary source). Code:
`libs/sources/algotrade_sources/vendors/ibkr/`, `apps/ingestion/.../tasks/reference/ibkr_contracts.py`,
`tasks/market/ibkr_iv.py`, `src/algotrade/data/volatility.py`,
`src/algotrade/features/rollups/ibkr_iv.py`, `config/site/features/volatility.toml`. Vendor
notes and owner commands: [docs/data/vendors.md](../data/vendors.md#ibkr).

## Context
Our IV rank (`iv_history@v2`) ranks our own IV30, computed from the nightly Cboe chains; it
needs 60 sessions before it shows a rank and 252 before it is FULL, so it is UNKNOWN for
months after a name starts trading options or after we start collecting. IB publishes a
daily 30-day implied volatility of each underlying's options (and a 30-day historical
volatility) going back years, through the same read-only gateway the live verification uses.
That data is licensed for the account holder's personal use, unlike our own computations.

## Decision

### Read-only, unchanged
Every request goes through the facade (`gateway.py`, ADR 0026) and only through calls
already on its allowlist: `qualifyContracts` (contract ids), `reqHistoricalData`
(`OPTION_IMPLIED_VOLATILITY`, `HISTORICAL_VOLATILITY` daily bars), `reqMktData` /
`cancelMktData` (generic ticks 106 and 104: the underlying's option implied vol and
historical vol, streamed). No call was added; order and account calls stay blocked (tested),
and the AST guard is unchanged. Tick 106 was confirmed on delayed market data (type 3) on a
paper login on 2026-10-03.

### Two tables, one producer each
- `instruments/ibkr_contracts` (task `ibkr-contracts`, `tasks/reference/`): per instrument of
  the option-chain coverage, IB's `conid`, primary exchange, security type, currency and
  `resolved_at`. Snapshot runs (rows carried forward). New optionable names and renamed
  symbols are resolved the same night; every other name once per `[ibkr]
  contracts_refresh_days` (30) on its own slot day (`refresh.due_keys`), so the monthly
  refresh is spread over the month. Read through `data.reference.ibkr_contracts`.
- `volatility/ibkr_iv30` (task `ibkr-iv`, `tasks/market/`): instrument x session,
  `iv30_ibkr`, `hv30_ibkr`, `source_kind` (`history`: IB's daily bar; `snapshot`: the value
  streamed after the close). Merge runs: the latest run's row wins per instrument, so a later
  history backfill replaces a snapshot. Read through `data.volatility.ibkr_iv30` and the
  feature input of the same name.

### Pacing, backfill and the nightly
IBKR's historical-data rules: no identical request within 15 s, no 6+ requests for one
contract and tick type within 2 s, at most 60 requests per 10 minutes (the last is enforced
strictly for bars of 30 s or less; larger bars are "soft"-throttled, at most 50 open at once).
We keep the conservative shared limiter `ibkr_historical` (`historical_min_interval_s = 10`,
i.e. 60 per 10 minutes) for every historical request, the live verification's included.

- A **backfill** (`algotrade-ingest run ibkr-iv --from D1 --to D2`) makes ONE request per
  series per underlying for the whole range (2 requests: IV and HV). At 10 s each that is
  20 s per underlying: the ~4.2k optionable names take **about 23 hours**. It is resumable
  per underlying, within a run (`resume`) and across runs (an underlying whose history an
  earlier finished run fetched from the same start or earlier is skipped), and `--limit N`
  caps a run, so the owner spreads it over nights or a weekend.
- The **nightly** step (`ibkr-iv`, after `chains` and `ibkr-contracts`, before `rollups`)
  streams every underlying's IV and HV in batches of `[ibkr] iv_batch` (50; paper accounts
  have about 100 market-data lines), paced by the general limiter (50 messages/s): a few
  minutes for 4.2k names. It then backfills the history of up to `[ibkr]
  iv_backfill_per_night` (100) underlyings that have none yet (new names; the initial
  backfill spread over nights), about 33 minutes. Both IBKR steps are SKIPPED with a WARN when
  `[ibkr]` is disabled or the gateway is down; the email shows IBKR IV coverage, backfill
  progress (pending, estimated hours left) and the `ibkr` / `ibkr_historical` pacing.

### Features: IBKR first, ours as the fallback, always labelled
- Group `ibkr_iv@v1` (window kind): `iv30_ibkr`, `hv30_ibkr`, `iv_rank_252d_ibkr`,
  `iv_percentile_252d_ibkr`, `history_days_ibkr`, `rank_status_ibkr`, with exactly the rank
  rules of `iv_history@v2` (same function, same 60 / 252 thresholds in `rollups.toml`).
- Expression features (`config/site/features/volatility.toml`): `iv_rank` =
  `coalesce(ibkr rank, our rank)`, `iv_percentile` likewise, and `iv_rank_source` (`ibkr`,
  `ours`, or null when neither has a rank). A consumer that shows `iv_rank` shows its source.
  When IBKR is down for a session, `ibkr_iv@v1` has no rows for it and the fallback applies
  with the label `ours`.

### Licence tags
`Feature` gains `licence`: `open` (our computation from free data, the default) or
`personal` (derived from a personal-use market-data licence). Every `ibkr_iv@v1` feature is
`personal`; an expression feature takes the most restrictive licence of its inputs, so
`iv_rank`, `iv_percentile` and `iv_rank_source` are `personal`. The licence is in the feature
catalogue (`docs/data/features.md`) and the API's `/features` output. Today there is one
user (the account holder); when there are others, the API will hide `personal` features from
users other than the owner (a later change, recorded here).

## Consequences
- IV rank is available from day one for names IB covers, labelled `ibkr`; ours remains the
  fallback and the cross-check, labelled `ours`.
- A full backfill is a long, resumable job (about 23 hours at the default pace); the nightly
  grows by a few minutes for the snapshot plus up to ~33 minutes of capped backfill.
  Lowering `historical_min_interval_s` for daily bars is possible under IB's rules but is the
  owner's call after watching the pacing stats.
- Data derived from IBKR is personal-use: it must not be exposed to other users without
  revisiting this ADR.
