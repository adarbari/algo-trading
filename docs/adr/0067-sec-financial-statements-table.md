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
would therefore find every CIK due for the statements (~6k documents, about 15 GB of raw files kept
7 days, one ~5M-row publish, an hour added before the critical steps), so the backlog is capped:
`[sec_edgar] statements_backfill_per_night` (default 400, 0 = no cap) bounds the CIKs that have a
shares marker but no statements marker fetched a night. A CIK new to both tables, or due for its
shares by its slot, is never capped. Deferred CIKs count in `deferred_by_limit`; the backfill
finishes by itself in about 15 to 20 nights with no manual run (`algotrade-ingest run shares --limit N`
remains for a chunk by hand). What is due is worked out from `cik` and `fetched_on` alone (a
maximum over the stored rows) and the key rows are read only for the instruments fetched that
night. A document whose statements do not parse still stores its share counts and leaves the
statements marker unwritten, so the CIK stays due for them.

Reads are `data/statements/reading.py` (a new folder: `data/` is at its module cap): `stored_statements`
for the producer, `statement_facts(reader, session)` the facts filed on or before a session.

### The parser stores every tag; rollups choose
`statement_concepts.py` lists the us-gaap tags of each concept, best first (39 tags after the 2026-10-17 amendment, 16 concepts,
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
  another), read at the balance sheet date (`bs_as_of`, the newest date of the core lines), first rule
  that applies: (a) `LongTermDebt` + `ShortTermBorrowings`, else `CommercialPaper` (short-term borrowings
  usually include commercial paper: never both); (b) `LongTermDebtNoncurrent` + `LongTermDebtCurrent` +
  `ShortTermBorrowings`, else `CommercialPaper`; (c) `DebtCurrent` + `LongTermDebtNoncurrent`. Each rule
  needs its main (anchor) parts (`LongTermDebt`; both noncurrent and current portions; `DebtCurrent` and
  `LongTermDebtNoncurrent`); the short-term part is optional and a missing one counts as 0: the one place a
  missing figure is added as 0, because a filer without short-term borrowings has none (owner accepted). An
  incomplete set of main parts is null with `NOT_TAGGED`, not zero debt: a filer without the tags and a
  debt-free filer look the same in the document. Rules d to g (amendment 2026-10-17, below) follow a, b, c.
- **One balance sheet date.** Every line other than the core ones (cash, total assets, equity), total
  liabilities and debt are read only at `bs_as_of`; a line not reported at that date is null, never an older
  figure. Derived liabilities (`LiabilitiesAndStockholdersEquity` less equity) subtract the equity including
  the noncontrolling interest first, as the total includes it.
- **Financial-sector gating.** `is_financial` is SIC 6000 to 6411 (`instruments/company`). For these
  issuers the EBIT family (operating income, EBIT margin, interest cover, EV/EBIT, enterprise value
  from debt) is null: a bank's debt and operating income are not those of an operating company. ROE,
  ROA and price to book are kept.

### Amendment 2026-10-17: rules d to g for the lease-inclusive debt tags
Measured on the first fetched companies (non-financial, `bs_status` OK, 504): `debt_basis` was
`NOT_TAGGED` for 259 (51%). 70 of them tag `LongTermDebtAndCapitalLeaseObligations` at `bs_as_of`, the
most common balance sheet debt tag the lists lacked. Four tags are added to `debt` (35 to 39) and four
rules follow a, b, c, each from the parts of ONE accession at `bs_as_of`, never summing a total with
its own components, the short-term part (`ShortTermBorrowings`, else `CommercialPaper`) added only to a
part that excludes it:
- (d) `LongTermDebtAndCapitalLeaseObligations` (noncurrent) + `LongTermDebtAndCapitalLeaseObligationsCurrent`
  + the short-term part;
- (e) `LongTermDebtAndCapitalLeaseObligations` + `DebtCurrent` (which already includes short-term
  borrowings: none added);
- (f) `LongTermDebtAndCapitalLeaseObligationsIncludingCurrentMaturities` + the short-term part (a total
  like `LongTermDebt`);
- (g) `DebtLongtermAndShorttermCombinedAmount` alone (the carrying value of all short- and long-term
  debt: nothing is added).

The us-gaap definitions relied on, as the SEC's own descriptions in our stored documents read:
`LongTermDebtAndCapitalLeaseObligations` "long-term debt and lease obligation, classified as
noncurrent" (the description does not say finance leases only); `...Current` the same "classified as
current"; `...IncludingCurrentMaturities` the same "including portion classified as current";
`DebtCurrent` "short-term debt and current maturity of long-term debt and capital lease obligations";
`DebtLongtermAndShorttermCombinedAmount` "the aggregate of total long-term debt, including current
maturities and short-term debt" (it does not mention leases). Measured on the 987 stored documents
(architect review): of 213 filers tagging the noncurrent lease-inclusive figure, 149 also tag
`OperatingLeaseLiabilityNoncurrent` separately in the same filing; in none does the figure equal
noncurrent debt plus the operating lease liability, and in 6 it equals noncurrent debt plus the
finance lease liability. Also, on the 504 first fetched companies, total = noncurrent + current for
23 of 25 filings and the all-debt figure = noncurrent + `DebtCurrent` for 2 of 2 (within 0.1%).
So the figure is debt plus finance leases, not operating leases. **Owner-side decision
(2026-10-17): finance leases stay in `total_debt` under the rules whose tags include them, labelled
per rule; operating leases are never in debt.** Per rule: finance leases are in under d and f (both
parts), in the noncurrent part of e and its current part (`DebtCurrent` includes the current
maturity of capital leases), in the current part of the existing rule c, and not in a and b (long-term
debt and its current maturities); the tag of g does not say, so g is not claimed either way.
Unchanged: a filer with only a noncurrent figure (`LongTermDebtNoncurrent` or the lease-inclusive one)
and no current part stays `NOT_TAGGED` (understated debt is worse than null), and so does a filer
whose only tags are components or note items (`LineOfCredit`, `NotesPayable`, `SecuredDebt`,
`ShortTermBankLoansAndNotesPayable`, `FinanceLeaseLiability*`, `DebtAndCapitalLeaseObligations` whose
scope is not clear). Of the 259: 72 become tagged (d 46, e 15, g 8, f 3), 187 stay `NOT_TAGGED` (132 tag
no debt at all, 34 `LongTermDebtNoncurrent` without a current part, 9 the lease-inclusive noncurrent or
total without one, 8 short-term only, 4 a current part only); the 245 already tagged keep their rule and
value. Stored rows are only added to, and the parser keeps only listed tags, so companies fetched
before this change need a refetch. No manual run: `STATEMENT_TAGS_VERSION_DATE`
(`statement_concepts.py`) is the day the lists last grew, and the `shares` task counts a statements
marker older than it as backlog, refetched under the existing nightly cap (`backfill_per_night`, 400:
the ~800 already fetched take about two nights). `--force` is not needed and would refetch every CIK
(~6k) outside the cap.

## Consequences
- About 600 rows per company on average (median 386, largest of 114 sampled documents 1,815): ~5M
  rows for the universe plus the markers, against ~2.6M for `instruments/shares` (docs/data/nightly-footprint.md). The task reads the
  table by key columns only (and one donor instrument per CIK for a class that is new).
- `statement_facts` is read by feature inputs in a later PR; features may not import it directly
  (import-linter contract on `algotrade.data.*`, extended by this ADR with `data.statements`; the
  `feature-input-loading` ownership entry lists its call).
- The tag lists grow by editing `statement_concepts.py` and bumping `STATEMENT_TAGS_VERSION_DATE`
  there: the `shares` task refetches the older statements under the nightly cap, no `--force`; stored
  rows are only added to.
