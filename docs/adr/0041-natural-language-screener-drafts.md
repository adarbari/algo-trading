# ADR 0041: Natural-language screener drafts through a swappable text model

**Status:** accepted (2026-10-05; owner decision; implementation: roadmap NL1), amended
2026-10-06 (the prompt also carries two worked examples and a site phrasebook,
`config/site/phrasebook.toml`: trader vocabulary mapped to catalogue fields with threshold
hints, so a free model maps "momentum" or "near the low" the way the owner means; the owner
chose free providers and a phrasebook over a paid model), and again 2026-10-06 (a site
**field guide**, `config/site/field_guide/*.toml`: per catalogue field how to read it, the
usual criterion for each intent, the caveats where the number is right and the conclusion
wrong (a pending takeover pins RSI high and realised volatility near zero; an earnings gap
inflates a month of realised volatility), and the situations that fool several thresholds
at once; one source for the Builder's field help, the generated page
`docs/data/field-guide.md` and the prompt, because drafts chose the right fields but poor
thresholds; the owner wants the same explanation for people as for the model), and a third
time 2026-10-06 (**the text-model seam** has a second caller, the on-demand regime
explanation: `TextModel` moves to `services/text_model`, the explanation's prompt discipline,
number check and link filter, and an ADR 0005 write exception for its answer cache; see
"Amended 2026-10-06: the text-model seam"), and again 2026-10-08 (**a provider chain**:
`[[provider]]` tables in `llm.toml`, Claude first and Gemini Flash behind it, one
`Completion` result; see "Amended 2026-10-08: a provider chain"). Extends
[0027](0027-vendor-sources-shared-package.md) (an external text model is a vendor adapter in
`libs/sources`), [0029](0029-rule-screener.md) (a draft is still the only thing the Builder
edits), [0005](0005-ingestion-is-the-only-writer.md) (one derived-cache write exception) and [0037](0037-domain-read-model-served-by-graphql.md) decision 4 (a compute over a request body
stays REST).

## Context
A rule screen is a TOML document of criteria over a closed field catalogue, with modes,
tolerances and a fail-closed validator (`docs/screeners/rules.md`). Writing one in the Builder
means knowing the catalogue. The owner wants to type "optionable stocks over $5 with IV rank
above 50% and at least $50M traded a day" and get the rows.

Turning such a sentence into criteria is a bounded extraction task: the choice set (fields,
operators, modes) is explicit and small, and the existing validator rejects anything invented.
That makes a cheap or free hosted model, or a local one, adequate. What varies is the
provider: free tiers (Gemini, Groq, OpenRouter) change limits and model names every few
months, most reserve the right to train on prompts, and a local model (Ollama) keeps
everything on the machine at zero cost. A screen is the user's idea, so where the text goes is
a decision, not a detail.

The repository's boundaries decide where this lives: vendor HTTP exists only in
`algotrade_sources` (ADR 0027), the library never imports it, the API reaches the library
only through `services.*`, and the API never writes market or feature data (ADR 0005).

## Decision
1. **One interface, the provider in config.** The library declares a `TextModel` protocol
   (`services/drafting/model.py`): one call, system text plus user text in, the model's text
   out, raising `ModelUnavailableError` (`core`) when it cannot answer. The only adapter is
   `algotrade_sources/llm/chat.py`: an OpenAI-compatible chat-completions client over the
   sources package's own HTTP (`json_post_transport`; no vendor SDK), which covers Gemini,
   Groq, OpenRouter, Ollama and Anthropic's compatibility endpoint by `base_url` alone. A
   native Anthropic adapter is a follow-up, not a precondition. `config/site/llm.toml`
   (`LlmSettings`) names `base_url`, `model`, `timeout_s`, `answer_limit` and `enabled`
   (default off); the key comes only from `ALGOTRADE_LLM_API_KEY` (`config/env.py`), optional
   for a local server, and travels only in a header. A `base_url` that is not this machine
   must be `https`.
2. **A draft, never a write, never a run.** `services/drafting/screens.py` turns a sentence
   into a draft document: it renders the caller's catalogue (name, type, unit, one-line
   description) and the spec grammar into a frozen prompt, asks for JSON at temperature 0,
   parses it strictly, drops every criterion whose field is not in the catalogue (reported as
   `dropped`, with the model's own reason), and validates the rest with
   `resolve_rule_draft` exactly as finalise does. The API serves it as
   `POST /screeners/{id}/draft-from-text` (REST: compute over a request body); the response is
   the document plus what was dropped and the model's notes. The browser loads the document
   into the Builder's edited state as proposed rows; saving, preview and finalise are
   unchanged. The nightly never sees a draft the user did not finalise.
3. **What leaves the machine is the sentence and the catalogue.** The prompt carries the
   user's text, the Builder's current criteria and the caller's field catalogue: names,
   types, units, descriptions and category values, including the caller's own expression
   features (their names and descriptions, not their formulas). It never carries market
   data, results, user ids or credentials, and an error never echoes the key. The sentence
   is capped (1000 characters) and the call is one synchronous request bounded by
   `timeout_s`, never a job (ADR 0010). With a hosted free tier the owner accepts that the
   provider may train on that text; when that is not acceptable the config points
   `base_url` at a local server and nothing leaves.
4. **Repeatable, and offline in CI.** The adapter takes its transport as a callable; tests
   drive it with recorded responses and never the network (the root socket guard stays).
   The prompt is rendered from the catalogue in catalogue order with no timestamps, so a
   provider's prompt cache hits and a recorded test stays valid; the request asks for JSON at
   temperature 0. What is deterministic is the prompt and the parsing; a hosted model's
   answer is not guaranteed to be, which is why every answer goes through the validator.
5. **Boundaries.** One responsibility, `screen-drafting`, owns `services/drafting/*`, the
   adapter `algotrade_sources/llm/*` and the API's wiring `algotrade_api/drafting.py` (as
   `live-option-quotes` owns its three parts). The library use case imports the catalogue,
   the validator and `core`, never `algotrade_sources` (import-linter "Drafting is read-only:
   no writers, no jobs, no vendors"). The API builds the adapter through the source registry
   (`build_text_model`, so it imports no vendor module, as `live.py` builds the quote feed)
   and injects it; the route lives in `routes/drafting/` with its schema in
   `schemas/drafting/`. Off, or a model that does not answer: the endpoint answers 503 with
   the reason; the Builder shows it inline.

## Amended 2026-10-06: the text-model seam

The seam has a second caller. A regime explanation (docs/market-regime-plan.md 5.6, ADR 0047)
asks the same `TextModel` for plain words about the market weather.

1. **One seam, two callers.** `TextModel` (and `ModelUnavailableError`) moves to
   `services/text_model/model.py`, with a `name` (the model `llm.toml` names) so an answer can
   be cached per model; the API builds it once (`open_text_model`, `apps/api/algotrade_api/
   text_model.py`) and both routes get it from the one dependency. Ownership splits:
   `text-model-seam` owns the protocol, the adapter `algotrade_sources/llm/*` and the API wiring;
   `screen-drafting` keeps the screen prompt and parsing; `regime-explaining` owns the
   explanation (`services/explaining/`). The 503 reasons name "the text model", not drafting.
2. **Prompt discipline.** An explanation's prompt is the task (explain to someone who does not
   follow markets; describe, never advise; use only the facts and links given; under 150 words;
   name the one or two signals that matter most), the regime's facts (weather word, headline,
   the three scores, each indicator that is on or changed with its plain name, one line, value,
   verdict, lead time and false-alarm line; a card question adds that card in full) and the
   allowed links (the cards' reading lists). No market data beyond those numbers, no user data,
   no credentials, no free text from the page: the question is "what is happening?" or a card's
   plain name, and the route accepts nothing else. Rendered byte-stable. Nothing calls the model
   unasked.
3. **The answer is checked, not trusted.** It is a JSON object `{text, links}` (the adapter asks
   the provider for a JSON object), parsed strictly: anything else is `ModelUnavailableError`. A URL that is not an allowed link is dropped; the allowed
   ones become citations; markdown marks are removed. Every number in the text must be one of
   the facts' numbers, with the same sign and to the precision the text shows (the as-of date
   is not a fact); the check is magnitude and sign only, it does not read spelled-out numbers
   or units; one that is not withholds the whole
   answer (`checked = false`, a note, no text) and the page shows its templated text instead.
4. **A derived cache, an ADR 0005 write exception.** The API writes the model's raw answer,
   only when it checked, to JSON files under `var/cache/explanations/` through
   `storage/backends/text_cache.py` (the `TextCache` protocol, keyed by session date and a hash
   of the signals' verdicts, the question, the model and the prompt's version),
   like its live-quote log (ADR 0028):
   derived, losable (a lost file is one more model call), never read by a backtest or a screen.
   A cached answer is checked again on every read. Per-user rate limit: 6 model calls a
   minute (in memory; a cache hit does not count); a seventh is a 429 with `Retry-After`.
5. **REST.** `POST /regime/explain {question | card}` is a compute over a request body, the
   same class as `draft-from-text`; it is a POST, so it is not on the GET allow-list
   (ADR 0037 is unchanged).

## Amended 2026-10-08: a provider chain

The owner wants Claude first and Gemini Flash behind it, site-wide, so one provider's outage or
quota is not "drafting unavailable".

1. **`llm.toml` names a chain.** `[[provider]]` tables (`id`, `base_url`, `model`, optional
   `timeout_s`, `answer_limit`, `retries`, `[provider.request]`) are tried in file order; the
   top-level `timeout_s`, `answer_limit`, `retries` and `request` are their defaults. A file
   with no `[[provider]]` is one provider from the top-level `base_url` and `model` (the
   single-provider form, unchanged); both forms in one file is a `ConfigurationError`. Anthropic
   is reached through its OpenAI-compatible endpoint, so the one adapter serves every provider.
2. **Keys.** `ALGOTRADE_LLM_API_KEY_<ID upper>` per provider (`llm_key(id)` in `config/env.py`);
   `ALGOTRADE_LLM_API_KEY` stays the key of the single-provider form only. No variable name is
   written in TOML. A remote provider whose key is not set is left out of the chain with a
   WARNING; no usable provider is "the text model is off", with the variables to set.
3. **`Completion` replaces the bare string.** `TextModel.complete` returns
   `Completion(text, model, provider, input_tokens, output_tokens, latency_s, fell_back_from)`
   (`core/model/completion.py`); tokens are read from `usage.prompt_tokens` /
   `completion_tokens` and are `None`, never `0`, when the provider omits them. `TextModel.name`
   becomes `names` (the models that may answer, in chain order).
4. **`FallbackTextModel`** (`services/text_model/chain.py`, pure) asks the members in order and
   falls back only on `ModelUnavailableError` (logged at WARNING); any other error propagates.
   When all failed, the error names every provider with its own message. One `deadline_s`
   covers the chain: after it no further provider is started; a request already running keeps
   its own `timeout_s`. Unset, it is every provider's worst case added up (`timeout_s` x
   (`retries` + 1) plus the pauses); a value not above the providers before the last is
   refused, so a hanging primary can never use up the fallback's turn. A non-retryable 4xx
   (bad key, unknown model) falls back too but is logged at ERROR.
5. **The explanation cache is keyed by the model that answered.** A lookup tries each name in
   chain order; a put uses `Completion.model`. A fallback's answer is therefore never kept under
   the primary's name, and a primary-only chain never reads the fallback's answer as its own.
   A cached fallback answer is served while the primary is up again (the lookup tries every
   name): an answer is for the signals, not for the model, and is checked again on every read.
6. The draft and explanation parsers already tolerate a code fence around the JSON object
   (Anthropic's compatibility endpoint may ignore `response_format`); tests cover both.

## Amended 2026-10-08: the owner's Claude Code login, for the owner only

The owner has a Claude subscription and wants it to answer his own requests ahead of Gemini.

1. **`kind = "claude-cli"`** on a `[[provider]]` (default kind: the OpenAI-compatible one) runs
   Claude Code headless (`claude -p`) on the owner's Mac with `command` (an absolute path:
   launchd's PATH is minimal), `model` ("haiku", "sonnet"), `timeout_s` and `retries` (default
   0). It uses the owner's existing login (the keychain entry of the user running the API); no
   `setup-token`, no `CLAUDE_CODE_OAUTH_TOKEN`, no API key is read or passed.
2. **Owner-only, by policy.** A subscription login must not serve other users. `only_users =
   [...]` (user ids of `users.toml`; any provider may set it) limits a provider to them, and a
   `claude-cli` provider without it is a `ConfigurationError`. The chain skips a restricted
   provider without asking it for any other user, and for a call with no user: they go straight
   to the next provider (Gemini). `CallTag(use_case, user)` (`core/model/completion.py`) is passed
   by keyword to `TextModel.complete`; the screener draft (`screener-draft`) and the regime
   explanation (`regime-explain`) tag the viewer. `TextModel.names_for(user)` lists the models
   that user may be answered by, and the explanation cache is looked up only under those names, so
   nobody else is served an answer the owner's login wrote.
3. **Locked down.** argv list (no shell), the prompt on stdin, `--output-format json --model M
   --system-prompt S --safe-mode --tools "" --strict-mcp-config --setting-sources ""
   --disable-slash-commands --no-session-persistence` (`--safe-mode` turns off CLAUDE.md, skills,
   installed plugins and their hooks, MCP servers, custom commands and agents, and keeps the login;
   `--setting-sources ""` alone would not), a fresh empty temporary directory as cwd, and an environment of
   `HOME`, `USER`, `PATH` and `LANG` only (`config.env.claude_cli_env`: no `ALGOTRADE_*`, no
   API key, no OAuth token). Never `--dangerously-skip-permissions`; never `--bare`, which skips
   the keychain read, so the login would not be found. One run at a time (a lock that
   a waiting request holds for at most `timeout_s`, then it is "busy" and the chain falls back);
   the child runs in its own process group and a timeout kills the group. `only_users` ids must be
   in `users.toml` (the API turns the text model off with the reason otherwise). The cache key
   names the Claude provider's model as `claude-cli:<model>`, so no other provider's model of the
   same id shares it. `--max-turns` does not exist in the installed CLI (2.1.285); with no tools
   the run is one turn.
4. **Failures** (non-zero exit, timeout, `is_error`, not logged in, usage limit, a command that
   will not start) are `ModelUnavailableError`s that never quote stderr, so the chain falls back.
   `Completion.cost_usd` carries the CLI's `total_cost_usd` (a notional figure on a
   subscription; `None` when absent).

## Amended 2026-10-08: no real model call outside the owner's running API

The owner's Mac has `claude` logged in and an untracked `llm.local.toml` enabling a chain, so
a test, a gate, the real-app smoke (`ALGOTRADE_AUTH=off`, user `smoke`, config dir `config/`)
or CI could have reached a model. The socket guard does not stop a child process.

1. **One off-switch**: `ALGOTRADE_LLM=off` (`config/env.py` `llm_off`). `open_text_model`
   returns `None` with a reason before reading any file or key, so no `llm.local.toml` or `.env`
   can turn it on.
2. **Where it is set**: `tests/conftest.py` (at import and per test), the Makefile's test, gate
   and smoke targets (a target-specific export), `apps/web/playwright.real.config.ts` (the API
   it starts), and the CI workflows. The nightly and the owner's API never set it.
3. **Second layer**: the root autouse fixture refuses to start any process whose program is
   `claude` (patched `subprocess.Popen`, so the default `run_process` and shell strings are
   covered) and fails loudly; adapter tests inject a fake runner. Other processes (sleep,
   version control) are not refused.
4. **Pinned** by `tests/architecture/pipeline/test_llm_off.py` (workflows, Makefile targets,
   Playwright config, and every test that builds the text model or a `ClaudeCli`).

## Amended 2026-10-11: schema, validate-then-fall-through, one repair, order is tier
An answer the model gives is no longer "text or unavailable":
1. **Schema**: `services/drafting/contract/answer_schema.py` holds the JSON Schema of the answer
   (`{criteria, tie_break, notes}`, strict form). `TextModel.complete` takes an optional
   `schema`; a provider with `structured = "json_schema"` in `llm.toml` (top level or per
   `[[provider]]`, default `"none"`) is sent it (`response_format` json_schema, strict; the CLI's
   `--json-schema`, answer read from `structured_output`). `response_format` stays a refused
   `[request]` key. A provider that ignores it costs nothing: the local check always runs.
2. **Validate, then fall through**: drafting passes `accept=` (parse, schema check, the draft
   itself); an answer it refuses (`InvalidAnswerError`, a `ModelUnavailableError`) is recorded as
   a `rejected` row and the chain asks the next provider, not only on "unavailable".
3. **One repair**: before falling through, the same provider is asked once more (stage `repair`)
   with the question, its refused answer and the exact error; the next provider is stage
   `escalate`. At most two calls per provider, none started after `deadline_s`. A repair is best
   effort: it is skipped when its worst case would cut into the time reserved for the later
   non-last providers (`worst_s`, from `LlmSettings`; the last provider's repair needs only the deadline not
   to have passed), so the fallback keeps its turn and the deadline validation is unchanged.
4. **Order is tier**: no tier concept; the `[[provider]]` order is cheap first, strong last.

## Amended 2026-10-11: the prompt is a field index plus a per-sentence slice

The system prompt carries an index of every catalogue field (`name | type | unit`) and, in detail, only
the slice `services/drafting/retrieval.py` picks for the sentence (`PROMPT_VERSION` 2; ~12-14k tokens, was
~110k). A field with no detail is still valid; the golden set's recall test guards against a false "missing".

## Amended 2026-10-11: the A / B / C answer contract

The answer is additive over `{criteria, tie_break, notes}` (`PROMPT_VERSION` 3; every new key nullable, so
an answer of the old shape still passes): `formulas` (B1), `missing` (B2 / C) and `unresolved`.

- **B1 limits**: a formula is same-session, per-row maths over `group.column` names and other expression
  features: the expression language's operators and `if abs min max log sqrt ncdf clip coalesce is_null
  one_of exists`. No lag, window, rolling or history; anything over time is `missing` with
  `ROLLUP_FROM_STORED`. The prompt says so, and the server enforces it by checking the formula as a
  user feature (`FeatureSet.with_user`).
- **The server decides, the model proposes**: a formula needs the `draft_` name, no shadowed feature, an
  `inputs` list equal to the names it reads, and is dry-run once, on the accepted draft, on the request's session (no-value rate,
  range, criterion pass count, samples; a formula whose inputs are missing for the session is kept
  unsampled, and a dry run that fails never fails the draft). A formula that is a stored column or
  repeats a saved one is a repeat (below). At most 3 formulas, 3 unresolved terms with 3
  alternatives each and 5 missing items are read; the rest are cut with a note. The prompt shows the
  8 open backlog keys most relevant to the sentence. Anything else is returned in `formulas_dropped` with its reason.
  `missing` keys are matched to the backlog (`feature_backlog.toml`, by key or alias), else become new
  slugs; `closest` keeps catalogue names only; each `unresolved` alternative carries a criterion
  validated like any other.
- **Dedupe by fingerprint**: a formula whose fingerprint (`features/expressions/fingerprint.py`) equals a
  site feature or the trader's own is dropped and its criterion rewritten onto that field, with a note.
  Structurally different equivalents are merged by an admin by hand.
- **Never auto-applied**: the draft `document` holds only A criteria (and the default reading of each
  unresolved term). A formula and its criterion are pending and travel beside the document until the
  trader accepts the formula as their own feature; B and C are shown, never saved or run by the draft.

## Amended 2026-10-11: prompt headroom (index grouped, slice token-budgeted)

`PROMPT_VERSION` 5 (4 is the structured phrasebook thresholds). The field index is grouped: one `<prefix>.*` heading per prefix
(`rollup.price_stats@v2.*`, `feature.*`, `instrument.*`) and `name|type|unit` entries under it, so
the long prefix is not repeated on every line; a field is still named exactly (heading without the
`*` + entry), so a retrieval miss never becomes a false "missing". The slice is capped by tokens,
not only by counts: `select_slice(budget, weigh)` keeps the phrasebook and core fields, adds the
word matches' detail lines by relevance while the budget holds, then upgrades them to full guide
entries (caveats) by relevance; `PROMPT_BUDGET_TOKENS` is 13,000 (chars / 4) for the whole prompt,
so text added later (the task, open keys, a trader's own features) shrinks the slice, not the
2,000-token margin to the 15,000 cap. Measured on the 24 golden sentences (open keys padded to the
cap, a user with three expression features): the prefix 7,380 -> 5,184 tokens, the largest prompt
(`heavy-put-call`) 14,930 -> 12,892; no case lost an expected field. A bare entry name (`iv30`, several headings share some) is never
resolved silently: the draft is refused with the full candidate names, so the repair retry fixes it.

## Amended 2026-10-11: protective checks are suggestions, never applied silently

Owner decision (2026-10-11, final; `docs/decisions/log.md`). The live Haiku golden run passed about
40%: roughly 20% of the failures were scorer artefacts (`gt` vs `gte` at a boundary; `is_etf` vs
`security_type in [ETF]`), 55% over-scaffolding (unrequested `atr_pct`, `trend_state`,
`rel_volume`, `adv_usd`, ... that the task text asked for as "add that criterion"), 25% real model
errors. The checks a caveat names are worth keeping but never applied silently, as with a formula
or a missing feature. The answer gains `suggestions` (nullable; `services/drafting/contract/suggestions.py`):
`{field, op, value, mode, tolerance, on_miss, why, source}` with `mode` soft or score only. The
server checks one like a criterion (catalogue field, op, value, tolerance, the rule validator) plus
the mode; a hard or modeless one, an invalid one, or one past 5 goes to `suggestions_dropped`
with a reason, a repeat of a criterion of the draft (or of another suggestion) is dropped
quietly, and a suggestion is never placed in `document.criteria`. `ScreenDraft` and the REST draft
response carry `suggestions` and `suggestions_dropped`; the Builder shows a "Suggested" group the
trader accepts or skips (a later web PR). Prompt version 7 (6 is the phrasebook follow-up's): `criteria` holds only what the
sentence asks for, a caveat's check goes to `suggestions`, and a vague word (`heavy`, `volatile`)
with no threshold in the phrasebook or field guide is left out with a note (the three guide
notes that said "add" now say "suggest"). Largest golden prompt: 12,735 -> 12,873 (the fixed part cut: examples, rules, wordings listed per phrasebook entry) tokens (cap
15,000). Golden scorer: a part may carry `equivalent_ops` (the same value, an immaterial boundary),
`EQUIVALENT_READINGS` names readings that select the same instruments (`is_etf eq true` /
`security_type in [ETF]`), only `criteria` are scored, and the run reports the suggestions count.

## Amended 2026-10-11: explained parts (the answer says which words each item comes from)

Owner decision 2026-10-11 (`docs/decisions/log.md`, "Explained parts"): the review shows one card per
part of the sentence, the trader's quoted words, then "We read this as...", then that part's rows. The
words, the part an item belongs to and the kind of part must be the server's, because the browser
derives nothing (ADR 0038) and a model's copy of the trader's words is not the trader's words.

- **Model side** (additive, nullable, so every answer recorded before it still passes): the answer gains
  `parts: [{id, words, reading}]` (`p1`... in sentence order, at most 12) and a nullable `part` on each
  criterion, formula, missing item, unresolved term, suggestion and on `tie_break`. `PROMPT_VERSION` 8.
  A malformed `part` is never a reason to drop its item. The criteria of an unresolved term's alternatives
  carry none (the term has it).
- **Served side** (`ScreenDraft.sentence` the whitespace-normalised text, `ScreenDraft.parts`, new folder
  `services/drafting/parts/`): each part is `{id, words, start, end, reading, reading_source, kind, origin,
  criteria, dropped, formulas, unresolved, missing, suggestions, rank}`. The lists only reference items of
  the same draft (criteria ids, formula names, terms, the key or new slug of a missing request, the
  server-assigned suggestion ids `s1`...); criteria, formulas, missing, unresolved and suggestions stay
  the sources of truth. `parts` is null when the model gave none or none could be found, and the web then
  shows today's panel. The `part` tag is never in `document.criteria`: criteria are rebuilt from the
  known keys, so it cannot enter the saved spec or its hash (a test compares the document and its hash of
  one answer with and without tags).
- **Words** are the server's slice of the sentence. Each part's quoted words are found in order, after the
  previous part: exact on word boundaries, then ignoring case, then token by token with one edit allowed
  per token of four or more letters and no digit (a typo; also a swapped pair). A part whose words are not
  found after the previous one (so also a reordered or overlapping one), are over 200 characters or are
  malformed is dropped and its items fall back. `start` / `end` are **UTF-16 code units** (what the
  browser's `slice` counts; Python counts code points, converted on the server, tested with accents and
  an emoji). Text no part covers that holds a word other than glue or a connector (the vocabulary of
  "Amended 2026-10-17: connectors and glue between parts" below) becomes a `not_understood` part, so nothing is silently dropped; at most 12
  parts carry words (the last model parts give way).
- **Attribution** is deterministic, in order: the part the model tagged the item with; else the part
  whose words contain the item's `span` (unresolved, missing); else the first part whose words say a
  phrasebook entry for the item's field; else a catch-all part with no words: `kept` for a criterion
  carried over from the Builder's current document, `unplaced` for the rest. The default reading of an
  unresolved term and the criterion of a rewritten duplicate formula follow their term or formula.
- **Kind** is the server's, from the refs only: `needs_choice` (an unresolved term) over `formula` over
  `not_available` (a missing request or a dropped criterion) over `applied` (a criterion or the
  tie-break); a part with none of these is `not_understood`. Suggestions never change the kind and
  never make a part understood. `origin` is `words` (a located part of the model), `gap` (words no part covers, always
  `not_understood`), `kept` or `unplaced` (the two catch-alls, with no words).
- **Reading** (the model's one line, clipped to 160 characters) is kept only when every number in it is
  one of the part's own: a criterion's value or tolerance, a formula's number, a number in the name of
  a field the part uses (the 20 of `ret_20d`), read with `%` as a fraction and `k` / `M` / `B` as their
  multiple; a part with no rows of its own may repeat the numbers of its words. Else `reading` is null
  and `reading_source` is `server` (the web shows the rows alone, which are always shown). A reading of a
  part nothing points at is dropped.
- **Rank**: `rank_by X` is a thing the trader says, so `tie_break` carries a `part` and a part holds
  `rank: true`; without it "rank by ..." would show as not understood.
- **Cost**: the prompt grows by 413 input tokens (the task text and both worked examples) and the
  slice shrinks to hold the 13,000-token budget: `slice_for` now searches (halving) for the largest
  slice whose whole prompt fits, where its eight fixed steps had stalled on a plateau (two golden
  sentences were over 13,000 with the new text, 13,044 and 13,107). Every golden sentence is now at most
  12,999 tokens with a trader's three own features and a padded backlog (cap 15,000). Output grows by a
  line per part (about 40 tokens; the largest recorded answer plus 12 parts at their caps and the thinking allowance stays under 75% of the configured `answer_limit` of 8,000, a test; the 2,000 in `chat.py` is only a dataclass default the registry overrides); `why` and `notes` are kept (the Builder shows both: a dropped
  criterion's reason ends with its `why`, and the notes are saved with the screen).
- **Feedback** (ADR 0066): `draft_returned.payload.parts` keeps id, words, reading, kind, origin and
  the item count of each part, clipped; the words and readings are personal text and go with the
  payload under the same 12-month retention and the erase command.
- **Golden scoring** never scores the text of a reading. The case's `expect.explained` names the parts
  (words, kind, origin, optionally the reading source), the share of items the model placed itself and
  the parts not understood; the live run reports the share of items the model placed itself, of its
  parts located, the parts not understood and the share of readings that kept their numbers.

## Amended 2026-10-12: the phrasebook shortcut (no model call when the book says it all)

A sentence every clause of which the structured phrasebook entries (`[[phrase.criterion]]`, exact
thresholds) say is drafted with no model call: `services/drafting/phrasebook/resolve.py` (`resolve`:
the entries and where their words are) and `shortcut.py` build an answer in the model's own shape,
each criterion tagged with its part and the parts quoting the trader's words, and `draft_screen`
runs it through the same `_draft` and `_finished` as a model's answer (parsing, catalogue check,
validator, attribution, parts). `PROMPT_VERSION` is unchanged (the prompt is). A word that flips or
splits a meaning (negation, a comparative, "or", "then"), a number or word no entry covers, an
entry with alternatives, two entries that disagree or share a criterion, a phrase said twice, a
criterion the caller's catalogue or the validator refuses, and a phrase on a field the Builder's
`current` criteria already hold all go to the model; `current` is kept as it was and added to; a sentence that contradicts what an entry implies of a `current` row (the pullback entry also says `trend_state eq UPTREND`) goes to the model, and so do the range and approximation words (`from`, `to`, `around`, `within`, `between`), which are never filler. The
`instrument.status` = `ACTIVE` scaffolding the task text asks of the model is added when no entry
says it. The parts' readings are built from the entries' criteria and served with `reading_source`
`server` (the web marks them "check this reading"). The draft has `stage` `phrasebook`, no `call_id`
(there is no ledger row to point at: it cost nothing), a `prompt_version` of `phrasebook:<hash of the
structured entries>` on its `draft_returned` row (the version survives the payload's erasure) and the
payload says `"stage": "phrasebook"`; the request and feedback events are written as for any draft. Golden
replay and the live run score such a case as any draft (model `phrasebook`, cost 0): it says
nothing about a provider.

## Amended 2026-10-12: re-draft one part (scoped call, merge, daily cap)

Owner decisions 2026-10-11 (`docs/decisions/log.md`, "Fixing one part", "Cost control type", "Daily cap number"):
a trader fixes one explained part by picking another reading or editing its rows (no model call), or by
retyping just that part's words, which re-drafts only that part. This is the second.

- **Route.** `POST /screeners/{id}/draft-part`: a preview-style POST that writes no config (ADR 0037 decision 4;
  no GET, so the allow-list is unchanged). The body is the draft the browser holds (`sentence`, `parts`, `document`
  the Builder's current one with the trader's edits, and the items the parts point at: `dropped`, `notes`,
  `formulas`, `formulas_dropped`, `missing`, `unresolved`, `suggestions`, `suggestions_dropped`), the `part_id` and
  `new_words` (at most 200 characters), and the optional `draft_session_id`. The answer is `{draft, replaced_part_id}`:
  the whole merged `ScreenDraft`, which the browser swaps in. The body carries the whole draft (not only the
  parts) because the answer must carry the other parts' pending formulas, readings to choose, requests and
  checks, which the server keeps nowhere (the draft memory is per process and the API restarts at every deploy).
- **Nothing sent is trusted** (`services/drafting/redraft/request.py`, a 400 before anything is asked or
  counted): the sentence is normalised as a description is; each part's `words` is the sentence's own slice at its
  UTF-16 offsets (in order, not overlapping; an offset inside a character is refused); ids are unique; every id a part
  names is an item the draft holds (a criterion the trader deleted from the document since is only dropped from the
  part) and belongs to one part (a missing request may be named by two); the part retyped has words of its own (not
  the `kept` / `unplaced` catch-alls; a `not_understood` gap may be retyped); the sentence with the new words in
  place is at most 1,000 characters. `kind` is decided again, never read.
- **Scoped prompt** (`redraft/prompt.py`): the same system prefix as the whole draft's (task, examples, field index,
  byte for byte, so the provider's cache hits), a slice retrieved for the new words alone and capped at 1,200 tokens,
  the matched phrasebook entries and open keys; the user prompt asks for the same JSON with one part and lists the
  other parts' criteria as at most 24 fixed rows of at most 110 characters. Everything after the prefix is under 4,000
  tokens for every golden sentence as the new words, with a trader's own features and padded keys (a test); one
  `PROMPT_VERSION` (9) serves both prompts and a test pins the hashes of `TASK` and the scoped `ASK` to it, so an edit of
  either without a bump fails (design call 2026-10-12); the answer
  is the draft's shape for one part, short (a line of reading, no notes unless a word could not be mapped). The call
  is tagged use case `screener-draft-part` with the shared `PROMPT_VERSION`, so the usage log, the cost and the budget
  count it as they count a draft. It goes through the same asking path (`screens.ask_for_draft`: answer schema,
  validation as `accept`, one repair, next provider).
- **Merge** (`redraft/merge.py`): the part's own criteria (the ids it names) are replaced as a whole, with its dropped
  criteria, formulas, readings to choose, requests, suggestions and tie-break. The other parts win: a new criterion on
  the same field and operator as a criterion of another part (or one the trader added by hand) is dropped with the
  reason "set by another part" (kind `other_part`); a suggestion that repeats or rewrites one of those thresholds is
  not offered; a formula or term another part offers is not offered twice; the document's tie-break stays when another
  part owns it. What the document holds that no part names (added by hand) is the `kept` part. Ids stay unique (a new
  criterion, dropped criterion or suggestion that takes a held id is renamed). The document is validated as finalise
  does: a new criterion the validator refuses is dropped with its message; one of the trader's own that it refuses is a
  400 (the merge never drops what the trader has): their criteria and tie-break are validated **before** the prompt is
  built, so the model is never asked about a screen that cannot be saved, and the document is bounded (60 criteria, each
  with a `field` and an `op`). What only grows (notes, the dropped criteria, formulas and suggestions) keeps its newest 40 (the parts stop pointing at a dropped criterion that went), and a
  merged draft never carries more than 40 of any list, so it can always be sent back; the other parts' readings come
  back from the browser, so the feedback payload marks them `prior: client`; the request log gets only the requests the
  draft did not already have. The new part's reading is the model's only when nothing it described
  was dropped by the merge. The other parts keep their ids, words and readings; the offsets of the words after the new
  ones move (UTF-16 units, tested with an accent and an emoji). Hand edits of the retyped part are replaced; the web
  asks first (the owner's decision).
- **Daily cap** (`redraft/cap.py`, `llm.toml` `[limits] part_redrafts_per_day`, default 30, 0 turns it off): per user
  per exchange calendar day, **counted from the usage log**, not from a counter a restart resets: the calls of use case
  `screener-draft-part` of that user on that day **that returned an answer** (`data.usage.calls_of`, one per call id: more
  `ok` / `fell_back` attempts than `rejected` rows, so a repaired call counts; a call that only failed or was skipped by
  the budget does not). Only a call that returned a draft uses up a place (owner decision 2026-10-12): the place is
  reserved when the request is admitted, under a lock, so requests in flight count and cannot all pass the last place,
  and given back when the call fails, is refused or the merge fails. The recorder writes in the background, so this
  process also remembers the calls it made and counts the union (a call is counted once when it reaches the log; the
  place's token is swapped for the call's id as soon as the model has answered). A merge that fails after the model
  answered rejects the answer in the usage log (`reject_answer`, as for any answer the app cannot use), so the call nets
  to nothing there too (a test runs the chain, its ledger, the recorder and the cap together). One case is not netted and
  is accepted: the bare-name fallback of a whole description (`screens.ask_for_draft`) returns a draft under a call whose
  every answer was refused, so in the log that call counts as none; that path is `draft-from-text` and not a part
  re-draft, and a part re-draft that took it holds its place only in memory until a restart. The day is the exchange
  calendar date (owner decision 2026-10-12). One API process is assumed, as the usage ledger
  does (ADR 0058). A count that cannot be read fails closed (503). At the limit: `DailyLimitError`, HTTP 429 with
  `{detail, code: "part_redraft_limit", limit, retry_after_s}` and `Retry-After` (seconds to the exchange day turning),
  which the web shows its "limit reached" state on; the model is not asked and no feedback event is recorded. The
  limit is read for each request. It is a count of calls, not of dollars: `[budget]` still caps the spend.
- **Feedback** (ADR 0066, amended 2026-10-12): `draft_requested` / `draft_returned` with `scope` `part`, `part_id`,
  `old_words`, `new_words` in the payload; the request log gets only the re-drafted part's missing items.
- **Golden**: four recorded cases (`tests/fixtures/drafting/golden/redraft/`: a number changed, the other part
  wins, a hand-added row stays, a vague word made exact), replayed through the real `draft_screen` and
  `redraft_part`; never the text of a reading.
- **Not decided here**: the web states (limit reached, confirmation before replacing hand-edited rows) are the web PR's.
  Notes and the dropped formulas / suggestions of the replaced words stay in the merged draft (they have no part to go
  with).

## Amended 2026-10-17: connectors and glue between parts

The prompt told the model to "skip connectors" in a part's words, but the server treated only 14
words as glue, so what the model rightly left out came back as `not_understood` chips: `have`, `have`,
`but`, `are` for "growth stock which have grown twice as fast as S&P and have had a great start...";
`but`, `while`, `are`, `yet`, `although`, `show me`, `I'm looking for, basically` for six other
sentences of 2026-10-17. An LLM judge scored Claude's segmentation 15/34 for this alone (owner
approved the fix the same day).

- **One vocabulary**, `services/drafting/parts/connectors.py`. `JOINS` maps a phrase to a logic
  (`and`: and, but, yet, while, although, though, whereas, plus, also, as long as, so long as, only if,
  provided (that), with, then; `or`: or, either, otherwise; `and_not`: except (for), excluding, exclude,
  unless, without, but not, not, avoid, other than, rather than, minus, no); the longest phrase wins and
  only whole words match. `GLUE` is closed-class words that mean nothing alone (auxiliaries, pronouns,
  determiners, and fillers such as `show me`, `I'm looking for`). The prompt renders its connector list
  from `JOINS`, so what the model is told to leave out and what the server reads cannot drift (a test).
  The phrasebook's `MEANING_WORDS` rule is unchanged: negation and `or` still send a sentence to the
  model, and the shortcut's filler-only check uses `GLUE`, never `JOINS`.
- **Glue is never a chip; a negation is never silent.** A stretch no part covers that holds only
  glue and and-type connectors is no part. An and-type connector in it becomes the **`join`** (`and`)
  and **`join_words`** (the sentence's own slice) of the part that follows it, a located part or a gap;
  glue, and an and-type connector before everything, vanish (the first part has no join). A negation or
  an or (`or`, `not`, `no`, `except`, `without`, `unless`...: `or` / `and_not` joins) changes what is
  asked, so the model keeps it **inside** the words of the condition it changes ("not overbought",
  "except those reporting earnings this week"; "X or Y" is one part covering both sides, its formula)
  and the server fails closed: such a connector the model left out stays a `not_understood` gap
  (words: the connector, trimmed of the glue around it), carrying its `join` / `join_words`, anywhere
  it lies (between parts, before the first, after the last). A gap that also holds a content word
  stays `not_understood`, trimmed of glue and and-type connectors at its edges, carries the and-type
  join before it, and the one after it goes to the next part. Why: the web does not render `join` yet,
  so a negation the model dropped from the words and the server turned into a join would be lost to
  the trader. `join` is served on the REST `Part` (null when none lies between the parts, the first
  included); a re-draft keeps the join of the part it replaces and of every untouched part.
- **Prompt version 10**: the left-out list is rendered from the and-type `JOINS` only (and the kept list from the others); a part is one condition and its
  words are contiguous ("cheap stocks on P/E" is one part); a vague word is never defined by a
  criterion the sentence does not ask for (offer unresolved readings).
- **Still `not_understood`:** any content word no part covers (`cheap`, `ideally`, `still`), as before.

## Amended 2026-10-17: the golden judge

The structural score of `golden run` cannot see bad segmentation or wrong connector logic: on
2026-10-17 a manual judge found 9 of 17 Claude drafts with connector chips (a "but" or "show me" as
its own part) that the structural score passed. `algotrade-api golden judge` adds an LLM judge over
the same real drafts: each (sentence, compact draft) is scored 0-2 on segmentation, coverage,
logic and fidelity by one single-provider text model (use case `golden-judge`, its own prompt
version), with the named issue patterns counted per drafting provider (`golden/judge.py`,
rubric `golden/judge_prompt.py`). It is owner-run only: never CI (no network), never in the
request path (a draft is never judged for a user), and under the same guards as `golden run`
(`--yes`, `--max-calls`, `--budget-usd`, stop after three unavailable answers). It measures; it
never gates a draft or a merge.

## Amended 2026-10-17: a provider whose quota is exhausted cools off
`usage/llm_calls` on the owner's machine: the free Gemini (first in the chain) failed 19 of 43
screener-draft calls, mostly 429 `RESOURCE_EXHAUSTED` "exceeded your current quota" (a DAILY
quota) and some 503 "high demand", and the call took about 40 s (p50) before the chain fell back
to Claude, because `ChatCompletions` retried every 429 with a 20 s floor.
- **A 429 that says the quota is used up is never retried.** The adapter reads the body
  (`QUOTA_MARKERS` in `llm/chat.py`: a `...PerDay...` quota id, "exceeded your current quota",
  `insufficient_quota`; a per-minute Google quota still retries) and raises `QuotaExhaustedError`
  (a `ModelUnavailableError`) at once with a cool-off: `Retry-After` if given, else one hour for a
  per-day quota, else 15 minutes. The hour assumes no reset zone (Gemini resets at Pacific
  midnight, not UTC, so a cool-off to UTC midnight would skip a refilled provider for hours); a
  retry each hour costs one instant 429.
- **The chain skips a cooled-off member** without calling it until the cool-off passes
  (process-local, thread-safe). Each skip is a `failed` ledger row whose error says "cooling
  off"; the first is logged once at WARNING. A 503 keeps its retries; the chain's deadline
  bounds it.

## Consequences
- A sentence becomes a reviewable draft in one request; a hallucinated field becomes a
  dropped row with a reason, never a saved criterion.
- Switching provider is a config change (`base_url`, `model`, the key); no code knows which
  vendor answered. A broken free tier degrades to "drafting unavailable", not a broken Builder.
- The feature is off until `llm.toml` enables it; the repository ships with it off.
- A second adapter (native Anthropic SDK, structured outputs) is a new module behind the
  same protocol; it does not reopen this decision.
- Quality is bounded by the catalogue descriptions: a field with a vague description is a
  field the model maps badly. Improving `description` on a `Feature` improves drafts.
- Thresholds are bounded by the field guide: a field without an entry gets the model's own
  number. A bad threshold in a draft is fixed in `config/site/field_guide/`, with its source, once
  for the page, the Builder and the prompt; `make features-doc` regenerates the page.
