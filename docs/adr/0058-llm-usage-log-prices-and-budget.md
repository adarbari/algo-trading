# ADR 0058: LLM usage log, prices and budget

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
figure is for scale), `free` (0: a local server or a model declared `free = true`), `bound`
(the upper bound reserved for the call, charged when the actual cost is unknown or the attempt
failed), `unknown` (null: a skipped attempt).
`outcome`: `ok`, `failed`, `fell_back` (answered after an earlier provider failed),
`skipped_budget`.

### Prices are config; missing is an error
`config/site/llm.toml` gains `[[price]]` (`model`, `input_per_mtok`, `output_per_mtok` in USD,
or `free = true`). A remote provider whose model has no `[[price]]` is a `ConfigurationError`
(the text model is off with that message, as for any bad `llm.toml`): missing data never counts
as $0. A loopback server is free without an entry; `claude-cli` is `reported`.

### Budget
`[budget] daily_usd, monthly_usd, over = "free" | "refuse", reported_call_usd`, all optional
(absent: no cap; `reported_call_usd` defaults to 0.25). Day and month are exchange calendar date
and month. **Every ambiguity fails closed for a provider that spends** (`price` or `reported`);
a free provider keeps answering.

- **Reserve, then settle.** Before asking a spending provider the chain calls `admit`, which
  atomically checks that spent + already reserved + this call's **upper bound** stays within
  every cap and reserves the bound; `record` settles it to the actual cost. Concurrent requests
  therefore cannot together pass a cap, which is what "stops at the cap by construction" means.
  The bound: prompt characters / 3 x the input price + the provider's `answer_limit` x the
  output price; for a `claude-cli` login, `reported_call_usd`. A call whose bound would pass a
  cap is not made (outcome `skipped_budget`): `over = "free"` skips the spending providers and
  the free ones answer, or, with none left, `ModelUnavailableError`; `over = "refuse"` refuses
  every call once a cap is reached (503 with the reason).
- **Unknown cost is charged its bound**, `cost_basis = "bound"`: a priced provider that answers
  without usage, a login that reports no cost, and a **failed** attempt of a spending provider
  (a timeout after the provider worked may still have billed; a 4xx that billed nothing is
  charged too, the safe side). A skipped attempt cost nothing (`unknown`, null). Free providers
  are logged at 0 with `free`.
- **Seeded or refused.** The counter is in the API process and authoritative, seeded from the
  store at startup (`data.usage.spent_by_day`) so a restart keeps the day's spend. Until a seed
  succeeds every spending provider is refused, whatever `over` says; the seed is retried lazily
  with a growing pause (30 s up to 5 min) and the error logged. Free providers answer meanwhile.
- A `claude-cli` call whose reported cost exceeds `reported_call_usd` can pass a cap by the
  difference (the reservation was its assumed bound); size `reported_call_usd` accordingly.
- **A broken ledger** (an exception in `admit`) skips the spending providers; a failure to
  *record* a row is logged and the answer goes on (recording is fail-open; spending is not).
- **One API process is assumed**: a second would count only its own calls and could overspend
  by its share; running several needs a shared counter (a new ADR).
- A `[[price]]` with `free = true` on a key whose billing is enabled bypasses the budget: only
  declare a tier free that cannot bill.

### The write
The API's fifth write (after user configs, live quotes, on-request screen results and the regime-explanation cache), the narrowest: `UsageWriter` (a copy of ADR 0028's
`LiveWriter`) writes only `usage/*` tables; only the usage recorder imports it (import-linter);
text-model code imports no market-data writer and no jobs. The recorder is the live recorder's
design, both now subclasses of `storage/recording.py` `BatchRecorder`: a bounded queue, one daemon thread, one atomic run per batch (ADR 0022), a full queue
drops the row (logged), and nothing the recorder or the ledger does can raise into the request:
the chain catches it and the answer goes on.

### Reads over a range
`data/usage` reads `usage/llm_calls` over a **date range** (`table_range`), the second
exception to ADR 0036's one-session rule after ADR 0053's outcomes: spend is a time series, not
a fact of one session. It feeds the ledger's seed now and the Admin usage page in the next PR.
It is not a session-grain table: the read model never lists it as missing for a session.

### Amendment 2026-10-11: failures keep their detail

A trader saw "the model's answer is not JSON" and the log could not say why: the chain records
an attempt `ok` as soon as the provider answers, and the refusal happens afterwards in the
caller; a provider that raised kept no message. `usage/llm_calls` gains nullable columns `error`
(the message), `stage` (`provider`: the attempt raised; `answer`: the provider answered and the
caller refused), `sentence` (the prompt, clipped to 2,000 characters), `answer` (the raw text,
clipped to 8,000) and `prompt_chars` (system + user length; the system prompt is never stored).
They are null on every other row and on partitions written before (readers add the missing
columns as null; no migration). A failed attempt records them at once. A caller that refuses a
well-formed answer (`services/drafting/screens.py`, `services/explaining/regime.py`) calls
`reject_answer`, which reaches `FallbackTextModel.reject`: it writes a **second** row, outcome
`rejected` (a new `OUTCOMES` value), same provider, model, use case and user, `cost_usd` null
and basis `unknown`, so the `ok` row still carries the cost once and the budget never counts
it twice; the row's key is (`ts`, `provider`, `use_case`, `user`, `outcome`), so an `ok` row and
its `rejected` row never collide. The Admin read adds `failures` (the newest failed and
rejected calls) and `reliability.rejected`, which is shown on its own: a rejected row is no
call and no attempt, so `calls`, `attempts` and the rates leave it out. The failure detail is
admin-only like the rest of the page. What is stored is the user's own prompt and the model's
own text, so it can hold whatever a trader typed. Messages: the Claude Code adapter never
quotes stderr; the HTTP adapter keeps only the status and the provider's `error.message`, one
line of at most 120 characters with key-like tokens replaced, so a message is not guaranteed
free of every secret but carries no header and no pages of provider text. The ledger log line
of a rejection holds the reason and the answer's length, never the answer.

**Retention.** Stored prompts and answers are kept as long as the table is (indefinitely: no
retention window applies to `usage/*`), each clipped to 2,000 / 8,000 characters. A
retention limit is a later decision if the table grows.

### Amendment 2026-10-11: cached input is metered

The log under-reported input. The Claude CLI reports `usage.input_tokens` as the **uncached**
part of the prompt only (2 for a prompt of about 110,000 tokens) and the rest as
`cache_read_input_tokens` and `cache_creation_input_tokens`; the adapters kept the first and
dropped the others, so `input_tokens` read as a small number for a large prompt. An
OpenAI-compatible endpoint reports `prompt_tokens` **including** its cached part
(`prompt_tokens_details.cached_tokens` where it says).

`usage/llm_calls` gains nullable columns (older partitions read them as null; no key change):
`cache_read_tokens` and `cache_write_tokens` (int64; null = not reported, never 0), `call_id`
(one uuid4 hex per `FallbackTextModel.complete` call, shared by every attempt of it and its
`rejected` row), `prompt_version` (the caller's `PROMPT_VERSION`, passed in `CallTag`) and
`call_stage` (`CallTag.stage`: `first`, `repair`, `escalate`; named so because `stage` is the
failure stage `provider` / `answer`). `input_tokens` keeps meaning the regular (uncached) input
the provider reported; the chat adapter takes `cached_tokens` out of `prompt_tokens` so that
**input + cache read + cache write is the whole prompt** for every provider (a cached count above
the prompt's is not believed: input stays `prompt_tokens`, cache read is null, so the charge
never falls below prompt x price).

**Cost is conservative.** A `price` call is charged `(input + cache read + cache write) x input
price + output x output price`: cache tokens at the full input price (no cache price fields), so
a cached call never costs less than before this change. A `reported` call keeps the CLI's own
figure; an unknown cost stays the reserved upper bound. The usage page shows the whole input
wherever it shows input tokens, with the parts on the call. The server serves it as
`totalInputTokens` (ADR 0038: the browser sums nothing); it is null for a `reported` (Claude
CLI) row written before this amendment (`call_stage` null: its cache was never stored), and a
tally counts those in `callsWithoutTotalInput` instead of summing them. A chat row from before
is complete: its `prompt_tokens` already included the cache.

## Amended 2026-10-11: the stages are set by the chain
`call_stage` takes `first`, `repair` and `escalate` (ADR 0041, amended 2026-10-11): the chain
tags the retry of a refused answer `repair` and the first call to the next provider after a
refused answer `escalate`. Each attempt is still its own priced row; a refused answer also gets
its `rejected` row (no cost), all under one `call_id`.

## Consequences
- A paid provider cannot be added without its price, and a day's or month's spend stops at its
  cap by construction (the bound is reserved before the call, the counter moves before the write).
- Even one provider is wrapped in the chain, so every call is recorded.
- An existing `llm.toml` with a remote provider needs a `[[price]]` before it loads.
- The owner's subscription spend appears as `reported` rows: notional, counted against the
  budget (set the caps with that in mind, or declare the login's calls free by leaving it out
  of the chain).
