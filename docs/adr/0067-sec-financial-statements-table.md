# ADR 0067: Financial statement lines from the SEC document we already fetch

**Status:** accepted (2026-10-16; design: the architect's plan for `balance_sheet@v1`, owner
decisions 2026-10-16: a missing figure is null, never 0; the financial sector is gated at SIC
6000-6411). Extends [0007](0007-point-in-time-data.md) (the filing date is the point-in-time
date) and [0023](0023-feature-store.md) (rollups are the only readers of stored inputs). Code:
`libs/sources/algotrade_sources/vendors/sec/statement_concepts.py` and `company_facts.py`,
`apps/ingestion/algotrade_ingestion/tasks/reference/shares.py`,
`src/algotrade/data/statements/`.

## Context
The `shares` task downloads each company's whole SEC `companyfacts` document and keeps five
concepts of it (`instruments/shares`). Equity, assets, debt, operating cash flow, capex and the
income statement lines that ROE, ROA, price to book, debt to equity, free cash flow yield and
gross profitability need are in the same document and are thrown away. Fetching them again
would double the SEC requests; keeping them needs a table of their own, because the facts are
not shares and the roll-ups that read them (`balance_sheet@v1`, planned in `docs/data/technical.md`)
should not scan share counts.

## Decision

### A second table from the one fetch
`instruments/statements`, the same grain and merge pattern as `instruments/shares`: increments
merged across runs, one row per instrument, concept, **tag**, period start, period end and filing
date (a null `period_start`, an instant's or a marker's, equals another null). Columns:
`cik`, `symbol`, `concept`, `tag`, `period_type` (`INSTANT` | `DURATION`), `period_start`,
`period_end`, `filed`, `form`, `accn`, `fy`, `fp`, `value`, `unit` (`usd`), `fetched_on`. The write
owner stays the `shares` task: one fetch of a company's document feeds both tables (no new task, no
second request). A CIK is fetched when **either** table is due (the older of the two latest
`fetched_on`s decides; a CIK with no marker in one table is new there), and each table carries its
own `checked` marker. Consequence: a failure to stage the statements after the shares were stored
leaves the statements due the next night instead of 30 days later. The first run after this ships
therefore finds every CIK due for the statements: the backfill is `algotrade-ingest shares --limit N`
over several nights or one detached run (docs/data/vendors.md, "Backfill").

Reads are `data/statements/reading.py` (a new folder: `data/` is at its module cap): `stored_statements`
for the producer, `statement_facts(reader, session)` the facts filed on or before a session.

### The parser stores every tag; rollups choose
`statement_concepts.py` lists the us-gaap tags of each concept, best first (35 tags, 16 concepts,
checked against the 1,975 company documents in the store: every tag exists). `company_facts.py`
stores **every tag found**, in `tag`, and never picks one over another, adds or subtracts across
tags: the choice depends on what is public on each date and belongs to the rollup. The order is a
preference only for concepts whose tags are alternatives of one figure (`cost_of_revenue`, `cash`,
`equity`, `ocf`...); for `debt`, `liabilities` (which also stores `LiabilitiesAndStockholdersEquity`
so a rollup can derive liabilities as that total less equity) and `current` it only fixes the output
order. The rules of the flows stay: periodic forms only (10-K, 10-Q, 20-F, 40-F and amendments),
USD only, spans of 3, 6, 9 and 12 months for durations (cash flow lines are cumulative from the
fiscal year start), and per tag the first filing of a period plus the filings that changed the value
(a restatement). Instants (a balance sheet date) follow the same rule per (tag, date) and must
carry no start. A figure in another currency is dropped: those issuers have no statement lines.

### Rollup rules this fixes (applied by the later `balance_sheet@v1`, not here)
- **Null over zero.** A concept not tagged by a filer is null with a status (`NOT_TAGGED`), never 0.
- **`total_debt` from the parts of ONE accession** (never a part from one filing and a part from
  another), first rule that applies: (a) `LongTermDebt` + `ShortTermBorrowings` / `CommercialPaper`
  (those present); (b) `LongTermDebtNoncurrent` + `LongTermDebtCurrent` + `ShortTermBorrowings`;
  (c) `DebtCurrent` + `LongTermDebtNoncurrent`. No debt tag at all is null with `NOT_TAGGED`, not
  zero debt: a filer without the tags and a debt-free filer look the same in the document.
- **Financial-sector gating.** `is_financial` is SIC 6000 to 6411 (`instruments/company`). For these
  issuers the EBIT family (operating income, EBIT margin, interest cover, EV/EBIT, enterprise value
  from debt) is null: a bank's debt and operating income are not those of an operating company. ROE,
  ROA and price to book are kept.

## Consequences
- About 600 rows per company on average (median 386, largest of 114 sampled documents 1,815): ~5M
  rows for the universe plus the markers, against ~2.6M for `instruments/shares` (docs/data/nightly-footprint.md). The task reads the
  table by key columns only (and one donor instrument per CIK for a class that is new).
- `statement_facts` is read by feature inputs in a later PR; features may not import it directly
  (import-linter contract on `algotrade.data.*`, extended by this ADR with `data.statements`; the
  `feature-input-loading` ownership entry lists its call).
- The tag lists grow by editing `statement_concepts.py` and re-running `shares --force`: stored rows
  are only added to.
