# ADR 0057: LLM usage log, prices and budget

**Status:** accepted (2026-10-08, owner ask: track text-model tokens and cost so spend never
blows up). Amends [0005](0005-ingestion-is-the-only-writer.md) (a new API write, after
[0028](0028-ibkr-enrichment-source.md)'s live quotes), and states one more exception to
[0036](0036-session-strictness-for-reads.md)'s one-session rule (a read over a date range). Extends
[0041](0041-natural-language-screener-drafts.md) (the provider chain, amended 2026-10-08) and
[0007](0007-point-in-time-data.md) (the table's columns). Code:
`src/algotrade/services/text_model/{usage,ledger,chain}.py`,
`src/algotrade/storage/tables/usage_writer.py`, `src/algotrade/data/usage/`,
`src/algotrade/config/site/llm.py`, `apps/api/algotrade_api/text_model.py`.

## Context
The text model has a provider chain (Gemini free tier, Anthropic, the owner's Claude Code
login). Every call spends tokens, a paid one spends money, and nothing recorded how much, so a
loop, a busy page or a typo in a model id could cost real money before anyone saw it.

## Decision

### One row per provider attempt, `usage/llm_calls`
A call to the chain makes one attempt per provider it asks. Each attempt is a row, the failed
ones and the ones skipped for budget too (a failure is a signal and may still have billed).
Partition: `session_date` = the **exchange calendar date** of the call (New York), not the last
session: spend does not stop at weekends. Columns: the point-in-time ones of ADR 0007 (`ts` =
the attempt, `session_date`, `knowledge_ts` = the call time, `source` = `text_model`, `run_id`)
and `provider`, `model`, `use_case`, `user`, `input_tokens`, `output_tokens` (null when the
provider did not report them, **never 0 for unknown**), `latency_s`, `cost_usd` (null when
unknown), `cost_basis`, `outcome`, `fell_back_from`. Runs merge (each is a batch of attempts;
key `ts, provider, use_case`). No retention: a few rows a day.

`cost_basis`: `price` (tokens x the model's `[[price]]` per million), `reported` (the notional
`total_cost_usd` the Claude Code login reports: a subscription is not billed per call, the
figure is for scale), `free` (0: a local server or a model declared `free = true`), `unknown`
(null: tokens or reported cost missing, a failed attempt of a paid provider, a skipped one).
`outcome`: `ok`, `failed`, `fell_back` (answered after an earlier provider failed),
`skipped_budget`.

### Prices are config; missing is an error
`config/site/llm.toml` gains `[[price]]` (`model`, `input_per_mtok`, `output_per_mtok` in USD,
or `free = true`). A remote provider whose model has no `[[price]]` is a `ConfigurationError`
(the text model is off with that message, as for any bad `llm.toml`): missing data never counts
as $0. A loopback server is free without an entry; `claude-cli` is `reported`.

### Budget
`[budget] daily_usd, monthly_usd, over = "free" | "refuse"`, all optional (absent: no cap).
Day and month are exchange calendar date and month. Once either cap is reached: `over = "free"`
skips every provider that spends (`price` or `reported`; outcome `skipped_budget`) and the
free ones answer, or, with none left, `ModelUnavailableError`; `over = "refuse"` refuses every
call with `ModelUnavailableError` (503 with the reason). Only `price` / `reported` costs that
are known count: an `unknown` cost is not $0 but is not summed either (the usage page shows how
many there were).

The counter is **in the API process and authoritative**: `UsageLedger` holds today's and this
month's spend, adds each attempt synchronously (so a burst cannot outrun the background
write) and is seeded once at startup from the store (`data.usage.spent_by_day`), so a restart
keeps the day's spend. **One API process is assumed**: a second process would count only its own
calls and could overspend by its share; running several needs a shared counter (a new ADR). If
the store cannot be read at startup the counters start at zero and the error is logged.

### The write
A second API write exception, narrower than any other: `UsageWriter` (a copy of ADR 0028's
`LiveWriter`) writes only `usage/*` tables; only the usage recorder imports it (import-linter);
text-model code imports no market-data writer and no jobs. The recorder is the live recorder's
design: a bounded queue, one daemon thread, one atomic run per batch (ADR 0022), a full queue
drops the row (logged), and nothing the recorder or the ledger does can raise into the request:
the chain catches it and the answer goes on.

### Reads over a range
`data/usage` reads `usage/llm_calls` over a **date range** (`table_range`), the second
exception to ADR 0036's one-session rule after ADR 0053's outcomes: spend is a time series, not
a fact of one session. It feeds the ledger's seed now and the Admin usage page in the next PR.
It is not a session-grain table: the read model never lists it as missing for a session.

## Consequences
- A paid provider cannot be added without its price, and a day's or month's spend stops at its
  cap by construction (the counter moves before the write).
- Even one provider is wrapped in the chain, so every call is recorded.
- An existing `llm.toml` with a remote provider needs a `[[price]]` before it loads.
- The owner's subscription spend appears as `reported` rows: notional, counted against the
  budget (set the caps with that in mind, or declare the login's calls free by leaving it out
  of the chain).
