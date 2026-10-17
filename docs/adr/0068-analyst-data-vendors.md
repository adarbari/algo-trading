# ADR 0068: Analyst-data vendors, the probe and `analyst/vendor_access`

**Status:** accepted (2026-10-16; design: the architect's plan for the analyst-data track, PR 2
of its sequence). Extends [0012](0012-data-vendors.md) and [0027](0027-vendor-sources-shared-package.md);
follows the licence rule of [0028](0028-ibkr-enrichment-source.md). Code:
`libs/sources/algotrade_sources/vendors/{fmp,finnhub}/`, `framework/access.py`,
`apps/ingestion/algotrade_ingestion/tasks/analyst/`.

## Context
What analysts expect (revenue and EPS estimates, price targets, the buy / hold / sell split) moves
a stock before the report does, and we store none of it. Two vendors give some of it free:
Financial Modeling Prep (FMP) and Finnhub. Both limit the free plan hard and change what it
includes (on 2026-10-16 FMP served `period=annual` estimates and refused `period=quarter` with a
402; Finnhub served recommendation trends and refused `stock/price-target` with a 403). A feature
built on an endpoint the plan later takes away fails at night, so what a key may call must be
recorded, not remembered.

## Decision

### Two free-tier vendors, personal licence
FMP (`https://financialmodelingprep.com/stable`, key `ALGOTRADE_FMP_API_KEY`) and Finnhub
(`https://finnhub.io/api/v1`, key `ALGOTRADE_FINNHUB_API_KEY`), each a folder under
`libs/sources/algotrade_sources/vendors/` with its own `sources.toml` section (`[fmp]`,
`[finnhub]`), one limiter key and `licence = "personal"` (as Tiingo, IBKR: features derived from
them inherit it, ADR 0028). Finnhub is paced at its 60 calls a minute. FMP has a daily budget,
`[fmp] daily_budget = 200` (the plan allows about 250; the rest is a hand run's headroom): the
analyst tasks count their own FMP calls against it per UTC day over every run in any status
(`tasks/analyst/budget.py`) and an endpoint that would pass it is not asked.

### One namespace, `analyst/*`
Analyst tables live under `analyst/`; this PR adds only `analyst/vendor_access`. The adapters (FMP
estimates, price-target consensus and the grades summary; Finnhub recommendations) parse into
frames and store nothing: the feature groups and the nightly fetch are later PRs.

### The probe and `analyst/vendor_access`
`algotrade-ingest run analyst-probe` (by hand, in no workflow) makes one un-retried request per
endpoint and classifies the answer (`framework/access.py`): `ALLOWED` (a 200 with rows), `DENIED`
(401 / 402 / 403, or a 200 whose body says upgrade / restricted), `LIMITED` (429, a quota body, or
an empty payload for the covered name). Any other answer (a 404, a 5xx) is no verdict: that item
fails and no row is written for it. It asks for two names: AAPL, a mega-cap (rows named for the
endpoint), and CHWY, a mid-cap of the event-sensitivity scope list (rows `<endpoint>@broad`). The
free FMP plan serves only some symbols (402 for the others), so an AAPL-only probe could say
`ALLOWED` for an endpoint the scoped pull cannot use for most names.

First result, 2026-10-16, free keys: FMP answered AAPL on every endpoint but `period=quarter`
(402), and CHWY with 402 on every endpoint; the owner's manual test had NVDA and JPM answering 200
for grades and NVDA for annual estimates. So the plan is symbol-gated. The owner measured the
boundary with one `price-target-consensus` call per name on 2026-10-16: **15 of the 104 scope
names are covered** (most refused ones are leveraged ETFs and small or mid caps), **21 of 25
mega and large caps** and **2 of 25 S&P 500 mid-caps**. Free FMP is therefore a large-cap
source; the probe keeps reporting it and the table records it.
Finnhub answered `stock/recommendation` for AAPL and CHWY and refused `stock/price-target` (403).

The table has one row per `(source, endpoint)` with `status`, `http_code`, `rows`, a fixed-words
`note` (never the vendor's body) and `checked_ts`; the partition is the run's session. Runs merge
on the key inside a session, but a later session's partition is a new one, so the task re-stages
the latest earlier partition's row (keeping its `checked_ts`) for every `(source, endpoint)` that
got no verdict this run (a vendor with no key, a 5xx, an endpoint over the budget): the verdict
stored before stays across sessions, and `checked_ts` says how old it is.

### Designed, built in later PRs
- **FMP: a coverage-driven, rotating pull.** 200 calls a day cannot cover the universe, and the
  free plan covers few names (see the measurement above). The pull learns the covered set (a name
  answered with 402 is marked `NOT_COVERED`, not retried until the next probe) and spends the
  200 calls a day only on covered names among the scope list of ADR 0050 plus tier A / B names
  and the large caps, rotated, each name's estimates, targets and ratings refreshed on a cadence
  set by the budget. Broad coverage needs a paid plan: an owner decision, not made here.
- **Finnhub: a whole-universe rotation.** At one call a second the recommendation trend of every
  name is a few hours of calls; it is spread over nights.

### Built: the nightly snapshot (edge build D2, 2026-10-17)
`analyst-snapshot` (`tasks/analyst/snapshot.py`, an optional step of the nightly workflow, latest
session only) appends each night's slice to `analyst/estimate_snapshots`, keyed (`instrument_id`,
`source`, `kind`, `period`) per session partition: `ts` the fetch instant, `knowledge_ts` the run's
publish instant, never a vendor date, no earlier session's row replaced. Names: S&P 500 members and
the scope list. FMP spends three calls a name within `[fmp] daily_budget` on names due on the
`[fmp] refresh_days` cadence (never fetched first, then the stalest); a 402 name is `NOT_COVERED`
and waits four windows. Finnhub reads up to `[finnhub] per_night` names on its own
`[finnhub] refresh_days`. With neither key set the step is skipped with a WARN (a pass). The rotation
is read back from the run records' items. Every attempt of a vendor for a name also stores one
`kind = "coverage"` row (`period = "current"`, `status` OK / EMPTY / NOT_COVERED / FAILED, `ts` the
attempt), in the same table and on the same key, so a feature reads "the vendor refuses this name"
(NOT_COVERED) apart from "not fetched yet" (no row) and "the call failed" (FAILED) from storage, not
from run items; a refused name has that marker and no estimate rows.

### History starts at the first fetch
Neither vendor gives a point-in-time history: a value they serve today replaces yesterday's and the
vendor's own "history" is a restated series. We do not backdate it: a row's `session_date` and
`knowledge_ts` are the fetch (ADR 0007), the history of an estimate begins when we first stored it,
and an edge cannot be tested on analyst data before that.

### The key never leaves the transport
FMP takes its key only as `apikey=` in the query string. The registry's transport appends it to
every URL (`with_query_param`, as for FRED), so the URLs a source builds, the retry and error
messages that quote them and the raw-store paths never hold it; the retry loop and the sources see
the URL without it. Finnhub's key is an `X-Finnhub-Token` header. A refusal of the key or plan
(FMP 401 / 402, Finnhub 401 / 403) is raised at once, not retried: a retry spends a call of the
budget and cannot help. Tests assert that no exception text, URL a source built or stored raw path
contains the key.

## Consequences
- Two more keys in `.env` (optional: no key skips that vendor and the probe says so).
- A plan change shows in the table the next time the owner runs the probe; nothing re-checks it
  nightly until the fetch tasks exist.
- The probe spends 12 FMP calls a run; it counts against the daily budget like every FMP task.
- What the free plans mean for the features: forward P/E and the FMP estimates use fiscal-year
  (annual) figures only; quarterly consensus stays with the existing calendar groups (the 402 on
  `period=quarter`); price targets come only from FMP consensus (Finnhub's `price-target` is
  premium). FMP's coverage is symbol-gated, so the scoped pull is limited to the names the table
  says `ALLOWED` for.
- Consumer rules for the table (later PRs): a `DENIED` row older than 7 days by `checked_ts`
  counts as unknown and is re-probed before the fetch relies on it; `LIMITED` means "ask later",
  never "denied".
- The vendors can change or drop a free endpoint; the adapters are tested on recorded answers
  (2026-10-16) and the probe is how a drift is noticed.
