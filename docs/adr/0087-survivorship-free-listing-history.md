# ADR 0087: Survivorship-free listing history: Massive inactive tickers, delisting events and the delisting return

**Status:** proposed (2026-10-24; owner decisions 1 to 5 below taken 2026-11-01). Amends
[0053](0053-edges-hypotheses-outcomes-and-one-harness.md) ("Eligible names", the 2026-10-09
amendment on historical eligibility, the DELISTED outcome), [0013](0013-universe.md) (the universe is
survivors and the delisted alike), [0018](0018-figi-instrument-ids.md) (the id order for historic listings)
and [0050](0050-event-sensitivity.md) (delisted filers). 0053 is at the 1,000-line cap (`make filelen`
counts `.md`), so the amendments live here. Design record: the architect's hand-back of 2026-10-24.

## Context
The owner wants the first credible edge verdicts: 63 of 66 setups read `not_enough_data` because the
out-of-sample period starts 2026-04-01 and a verdict needs 40 independent decisions (`config/site/verdict.toml`).
The agreed path counts the years after each source paper's sample ended as out of sample. That is credible only
on a survivorship-free universe from 2010.

The premise "every earlier window uses today's snapshot" is half stale: since the 2026-10-09 amendment of 0053,
sessions before 2026-10-02 read `data.listings.universe_asof` (Tiingo `instruments/listing_history`, 24,451
listings, with S&P 500 intervals), so `pre_snapshot` no longer applies. Measured on the real store 2026-10-24:

- **Bars hold the delisted** on their trading days (Tiingo `bars_history` 2010 to 2024, Massive grouped daily
  after): 935 of 3,170 bars on 2010-01-04 belong to ids whose listing has since ended; `universe_asof` has a bar for
  over 99% of its names.
- **G1: 6,542 of 10,351 ended listings have no id** (Tiingo's fundamentals meta could not match a permaTicker).
  Qualifying listings with no id per session: 956 (2012-06-01), 1,461 (2018-06-01), 1,372 (2025-06-02). Most are
  not stocks (of 3,643 that match a Massive record: ETF 1,068, CS 616, ADRC 36, WARRANT 592, UNIT 330, FUND 221,
  SP 162, ETN 159).
- **G7: Tiingo's supported-tickers file lists a company's whole history under its last ticker and exchange.**
  Bankrupt names sit under OTC successor tickers the adapter drops (BBBYQ, SHLDQ, HTZGQ, RADCQ, SIVBQ, FRCB); of
  Massive's 6,057 CS / ADRC delistings since 2010, 2,082 have no Tiingo row for that ticker and 1,171 more have a row
  that runs past the delisting. Renamed S&P 500 members (ABC to COR, ANTM to ELV, BLL to BALL) miss the membership
  match: members outside the universe, 92 of 499 on 2010-01-04, 60 of 500 in 2015, 8 of 503 in 2024.
- **G2:** a delisted name is typed `COMMON_STOCK` from Tiingo `asset_type = Stock`, which includes preferreds,
  warrants and units.
- **G3:** a DELISTED outcome is measured to the last bar; the move after it (the delisting return) is not
  measured, so bankruptcies read as flat. That flatters distress, momentum and small-cap tests.
- **G4:** no delisting reason. **G5:** `optionable` of a delisted name is today's flag or the liquidity proxy
  (disclosed since 2026-10-09). **G6:** Tiingo's licence is internal / personal.

## Decision
1. **A second reference source, stored first.** Massive's reference tickers with `active=false` (free key, probed
   2026-10-24: ticker, name, `primary_exchange`, `type`, `cik`, `composite_figi`, `share_class_figi`,
   `delisted_utc` = the last trading day) are stored as `instruments/delisted_tickers`, a full snapshot per pull
   session (key `source, ticker, end_date`), `knowledge_ts` the write time, written by one ingestion task
   (`delisted-tickers`, `tasks/listings/delisted_tickers.py`). The date column is named `end_date`, so the
   end-date reader scan covers it: an identity read, never a feature. 23,557 rows, 24 pages (about 6 minutes at
   the free tier's 5 requests a minute). Its gaps are disclosed: `type` is null before 2017 (6,739 rows), FIGI
   coverage is 3 to 18% for 2010-2018 and 37 to 78% from 2019, CIK 79 to 97%, no OTC records, no ETFs before 2016,
   renamed companies absent.
2. **One merged `instruments/listing_history` stays the only table `universe_asof` reads** (PR2). The
   listing-history task pairs a Tiingo row with a Massive record by ticker with end dates within 7 days (6,237 of
   10,302 ended rows pair, 0 ambiguous measured); a Massive record with no Tiingo row becomes a `source = massive`
   row, its start date from the Tiingo row with the same permaTicker on any exchange, else it is dropped and
   counted. New columns `security_type`, `cik`, `figi`, `id_source`. **Id order (0018, amended):** (a) the
   `symbol_history` id; (b) the permaTicker (`EQ:TIINGO:<perma>`; the meta is also asked for the Massive-only
   tickers); (c) new: Massive's composite FIGI through `equity_id`, only when unique and not already an id;
   (d) no id, counted by reason. An id once given is never upgraded automatically; a record whose FIGI is already an
   id (482 measured) is a ticker change, never a new listing; `EQ:<symbol>` is never built.
3. **Types are point in time for delisted names** (PR2, same PR as the ids): `universe_asof` returns
   `security_type`; a delisted name uses its stored type, and only a null type falls back to the Stock proxy, which
   is counted. Otherwise warrants and units would enter as `COMMON_STOCK`.
4. **`events/delisting`** (PR5): one row per delisted instrument (key instrument id, last session): `reason`
   (ACQUIRED, BANKRUPTCY, STANDARDS, VOLUNTARY, UNKNOWN: from 8-K items 1.03, 2.01, 3.01, 5.01 and Form 25 /
   25-NSE in a window of -120 to +30 days around the last bar), `known_from` (the session after the Form 25
   acceptance, else after the last bar), `last_close`, `terminal_close`, `terminal_session`, `terminal_basis`,
   `delisting_return`. `knowledge_ts` is the write time, never the delisting day. Point-in-time rules: the universe
   ignores delistings (a name alive on S is in: not lookahead); a feature reads a delisting only when
   `known_from <= S`; the outcome label reads delistings in (S, T] whatever their `known_from` (0053's one
   exception to the one-session rule), as stored when the row is written. Only `data/listings` reads it.
5. **The delisting return** (PR6, `forward_returns@v3`, new columns `delisting_return`, `delisting_basis`): a
   DELISTED `fwd_return` is (1 + return to the last bar) x (1 + delisting return) - 1. The convention, in order:
   the first OTC close within 10 sessions after the last bar (CRSP's rule, fetched by permaTicker from Tiingo);
   else ACQUIRED counts as 0; else BANKRUPTCY or STANDARDS take the owner's rule (decision 1); else 0, counted. The
   report gets a `DELISTINGS` section (counts by basis and reason) and shows the zero-convention figure beside
   the verdict. The edge-leg version is bumped, so the first run after it is a full one.
6. **The run stamp `universe_basis` (`survivors` | `free`)** (asked for by the ADR 0065 amendment, PR #967, so a post-publication verdict knows what it was measured on). The harness writes it in each run's stats
   (`stats["universe_basis"]`, with `universe_basis_gaps`, the failed conditions) for the evaluated window
   `[from, to]`; `free` only when **all** hold, otherwise `survivors`:
   (a) the merged listing history (PR2) is the one `universe_asof` read, and the share of its qualifying
   listings alive in the window with no id is at most `max_no_id_share`; (b) the share of names that delisted
   in the window with bars to their last bar is at least `min_delisted_bars_share`; (c) `events/delisting` rows
   exist for the window's delisted names and the share with `delisting_basis` UNKNOWN is at most
   `max_unknown_delisting_share`; (d) the window's outcomes are `forward_returns@v3` (the delisting return
   applied); (e) the share of names with a null `security_type` is at most `max_null_type_share`. Until
   PR2 and PR6 exist the stamp is always `survivors`. The thresholds live in `config/site/verdict.toml`
   `[universe_basis]`; **proposed values** (the owner can change them): 1%, 98%, 5%, 5%. Null types before
   2017 (6,739 Massive rows) may keep early windows `survivors` until a proxy or another type source is
   accepted: that is the intended answer, not a bug. The predicate is computed in `services/evaluation`
   from counts the data layer returns (`data.listings`); the verdict rule reads only the stamp.
7. **Left disclosed:** G5, G6, null types before 2017, ETF closures before 2016, renamed S&P 500 members until PR7,
   and that the NASDAQ rule uses each name's final exchange (G8).

## Plan (PRs; PR4 and PR5 are file-disjoint after PR2)
PR1 this ADR, the adapter, the table, the task, the reader and tests, not run on the real store. PR2 merge, ids
and types (architect review). PR3 the owner's runs (below). PR4 the `filings` task for delisted CIKs (the D1 / D10
Form 25 follow-up; built: `filings --delisted [--since]`, per CIK over the listing history's ended in-scope stocks with an id and a CIK from 2010-01-01, `since` defaulting to 2009-01-01, never the daily walk and no `walked_to`). PR5 `events/delisting` (architect review). PR6a `forward_returns@v3` written beside v2 (built), PR6b the harness
disclosure and the `universe_basis` stamp (architect review). PR7 S&P 500 renames through Massive ticker events (probe first) and the 2024-26
`EQ:<symbol>` bars migration (800 listings with no id have bars stored under `EQ:<symbol>` on 2025-06-02).
PR3b (not in PR2): Massive ticker details `/v3/reference/tickers/{T}?date=D` are point in time (`list_date`,
`figi`; probed 2026-11-01: BBBY on 2023-05-02 answers the old Bed Bath & Beyond, its `list_date` 1992-06-04) and
fill the start a Massive-only record still lacks (`no_start`, `perma_ambiguous`: Tiingo's meta for `bbby` answers a
reused ticker's permaTicker, so PR2 leaves BBBY undated). PR2 keeps every Tiingo row and every Massive record (owner
tenet 2026-11-01): a record whose start no Tiingo row gives is written with a null start and its reason in
`no_id_reason`, never dropped (Decision 2's "dropped and counted" is superseded).
**PR3b built (2026-11-03):** `MassiveTickerDetails` (`massive_ticker_details`, request key
`TICKER|YYYY-MM-DD`, 404 = not found) and the `delisted-details` task (in no workflow, `--limit`,
resumable) store every field of the answer in `instruments/delisted_details` (`runs="merge"`, one row
per asked (ticker, `end_date`), a not-found marker never asked again); asked at `date = end_date`
for the `source = massive` rows with a null start and the reason `no_start`, `perma_ambiguous` or
`no_meta`, stock types first, newest first. `merge_listings` takes the details' `list_date` as the
start when the details row is found, `list_date <= end_date`, the CIK and composite FIGI agree
where both exist, the details' `delisted_date` is within `PAIR_DAYS` of the record's end, and no
in-scope Tiingo row of the ticker overlaps the dated life; each refusal is counted
(`details_mismatch`, `details_after_end`, `details_overlaps`) and keeps the old reason, never
`pair_ambiguous` or `overlaps_listing`. The new column `start_source` (`tiingo`, `perma_successor`,
`massive_details`) says where a start came from (absent in older partitions, read as null). Ids are
unchanged: a details-dated record gets an id only by FIGI.

**PR5 built (2026-11-03):** `events/delisting` (`storage/tables/schemas/events.py`, a full snapshot per run
session, key instrument id + last session) written by the `delistings` task
(`tasks/listings/delistings.py`, the pure reason rules in `delisting_reason.py`; in no workflow; stored data
only: the listing history through `data.listings.universe.delisted_listings`, the instrument's `events/filing`
rows through `data.events`, the closes through `SessionBars`, the outcomes' basis). A row per delisting: an id
whose listings have all ended, and each ended listing of an id that relisted more than 10 sessions later (a
delisted name that came back is delisted once per gap; a ticker change is not). The reader is
`data/listings/delistings.py` (`read_delistings(reader, as_of_write, as_of)`: the latest snapshot on or before a
write session, never a later one, optionally pinned to what was stored by an instant; `known_by(frame, S)` for a
feature), which also holds the vocabulary and the convention for an instrument with no OTC print (decision 5,
owner decision 1). Choices the ADR left open: the last bar is searched within 30 days before the vendor's last
trading day and anchors the -120 / +30 day window; only a Form 25 filed by the issuer (or its amendment) decides
VOLUNTARY, while a 25-NSE counts for `known_from` only; `known_from` is the session after the later of the earliest
notice and the filing that decided the reason, so a row is never public before the filing it was judged from; a
bankruptcy or listing-standards delisting with no OTC print uses the final exchange (NASDAQ -55%, else -30%).
The table is current knowledge, so a run FAILS for a session before the listing history it reads was written, with
no listing history, and with no row. Its stats give rows by reason and by basis, `no_last_bar`, `no_filings` (PR4's
backfill gap), `no_cik` and `unknown_share` (decision 6 (c)). An AST scan allows only the reader, the writer, the
outcomes task (PR6a) and `services/evaluation` (PR6b) to import the reader.

**PR6a built (2026-11-03):** the `outcomes` task writes `forward_returns@v3` (v2 columns + `delisting_return`,
`delisting_basis`) beside v2 each night, one computation of each window; a `--from/--to` backfill writes both (a v3-only backfill left the v2 readers, the golden edge included, without outcomes).
v2 keeps its meaning (a test pins its rows equal to the pre-v3 output). The delistings come from the latest
`events/delisting` snapshot at write time (never as of S or T, whatever `known_from`), applied only when the
event's `last_session` is in (S, T] and is the name's last bar; max return, drawdown and volatility stay to the
last bar. A DELISTED row with no such event is `NO_EVENT` with no return. Readers keep v2 through
`data/outcomes/reading.py` `READ_TABLE`; PR6c flips it after the owner's backfill. Share path and residual returns
are untouched (PR6d).

**PR6b built (2026-11-03):** the run stamp and the disclosure. `data/listings/basis.py` `universe_basis_counts(reader, start,
end, as_of)` counts, from the latest listing snapshot and the delisting snapshot stored by `as_of`, the qualifying listings
alive in the window and those with no id, the stock listings with a null `security_type`, whether the snapshot is the merged
one, and the window's delistings with an event row, with an unknown basis (a missing event is unknown) and by reason and
basis. The pure predicate `services/evaluation/cross_section/run/universe_basis.py` writes `stats["universe_basis"]` and the
sorted `stats["universe_basis_gaps"]`; the limits are `verdict.toml [universe_basis]` (1%, 98%, 5%, 5%), typed apart in
`config/edges/universe_basis.py` (never in `settings_hash` or the judge digest). Gaps besides the four shares: `outcomes_not_v3`
(always while `READ_TABLE` is v2, so every stamp is `survivors` until PR6c), `grain_without_delisting_return` (share path,
residual or option chain: PR6d), an unmerged history, no counts read, an empty window, no delisting snapshot. A leg's picks gain
`delisting_basis`, `zero_value` and `zero_hit` (`apply_outcome` runs again on the zero view, the stored delisting return taken
out: `(1 + f) / (1 + dr) - 1`); `LEG_VERSION` 6, `DRAW_LEG_VERSION` untouched. `stats["delistings"]` and a DELISTINGS report line
give counts by reason and basis and the headline beside the zero figure. The verdict rule reads only the stamp.

**Backfill** (detached, README "Long runs"): Massive inactive list ~6 minutes; Tiingo meta ~35 batches; Tiingo bars
for the new ids plus the tails ~9,000 to 11,000 requests, 1 to 1.3 hours at 0.4 s, which holds only on the Power
plan (ends 2026-11-09; the free tier would take about 20 months); SEC submissions for ~6,000 delisted CIKs 30 to
60 minutes, free; then the pending `outcomes` backfill from 2010 once (bars grow about 12%).

## Owner decisions
Taken by the owner in the session's chat on 2026-11-01:
1. **Delisting return of a bankruptcy or listing-standards delisting with no OTC print: decided, option (a)**,
   the CRSP-style replacement, -30% NYSE / AMEX and -55% NASDAQ (Shumway 1997; Shumway and Warther 1999), the
   zero figure shown beside the verdict. Owner: "Ideally anything delisted if the setup suggests buying them it is
   a problem we should pick any options which penalizes picking a delisted stock is traded."
2. **Tiingo Power: decided, pull the data now.** Owner: "let us pull the data. we still have enough time to do it.
   Let us start the backfill immediately." The Massive list was started the same day. The Tiingo bars for the new
   ids need PR2's ids first, so they start when PR2 has merged; the Power plan ends 2026-11-09, and if PR2 and that
   pull cannot both finish before then, the renewal is raised again with the owner (it is not assumed either way).
3. **Hold the 2010 `outcomes` backfill and `evaluate-edges` until PR3 is done: decided, as recommended**: otherwise the first
   verdicts are survivor-tilted and are re-run.
4. **ETF closures before 2016 stay out of the universe, disclosed: decided, as recommended** (matters only for ETF edges).
5. **Norgate Platinum ($630 a year; delisted names to 1990, index history): decided, not now, as recommended.** Its licence is Personal Use only (no
   commercial use, no redistribution, derived data not stated to be showable to others), so it is not a source for
   statistics shown to paying users. At most an owner-only cross-check.

## Consequences
- Free sources only (Massive, EDGAR, Tiingo already held); no new paid dependency unless decision 5 changes.
- A verdict from 2010 onward measures names that were listed then and left, with a stated terminal return; the
  remaining tilts are named in the run record.
- Two new tables (`instruments/delisted_tickers`, `events/delisting`) and `forward_returns@v3`; ownership entries
  in `architecture/*_ownership.toml`, `architecture/tables.toml`; the end-date scan test lists the new readers.
- Risks: ticker reuse (match only when unique); a delisting read before its `known_from` is lookahead; a delisting
  stored late leaves `NO_END_BAR` until `outcomes --from/--to` is re-run (the delistings task lists the affected
  window ends); duplicate ids for one company after 2024-10 (`EQ:<symbol>` bars and a new FIGI id) until PR7.
