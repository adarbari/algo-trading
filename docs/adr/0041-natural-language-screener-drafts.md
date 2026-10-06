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
"Amended 2026-10-06: the text-model seam"). Extends
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
   the provider for a JSON object). A URL that is not an allowed link is dropped; the allowed
   ones become citations; markdown marks are removed. Every number in the text must be one of
   the facts' numbers, to the precision the text shows; one that is not withholds the whole
   answer (`checked = false`, a note, no text) and the page shows its templated text instead.
4. **A derived cache, an ADR 0005 write exception.** The API writes the model's raw answer,
   only when it checked, to JSON files under `var/cache/explanations/` through
   `storage/backends/text_cache.py` (the `TextCache` protocol, keyed by session date and a hash
   of the signals' verdicts, the question and the model), like its live-quote log (ADR 0028):
   derived, losable (a lost file is one more model call), never read by a backtest or a screen.
   A cached answer is checked again on every read. Per-user rate limit: 6 model calls a
   minute (in memory; a cache hit does not count); a seventh is a 429 with `Retry-After`.
5. **REST.** `POST /regime/explain {question | card}` is a compute over a request body, the
   same class as `draft-from-text`; it is a POST, so it is not on the GET allow-list
   (ADR 0037 is unchanged).

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
