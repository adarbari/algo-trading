# ADR 0041: Natural-language screener drafts through a swappable text model

**Status:** accepted (2026-10-05; owner decision; implementation: roadmap NL1), amended
2026-10-06 (the prompt also carries two worked examples and a site phrasebook,
`config/site/phrasebook.toml`: trader vocabulary mapped to catalogue fields with threshold
hints, so a free model maps "momentum" or "near the low" the way the owner means; the owner
chose free providers and a phrasebook over a paid model). Extends
[0027](0027-vendor-sources-shared-package.md) (an external text model is a vendor adapter in
`libs/sources`), [0029](0029-rule-screener.md) (a draft is still the only thing the Builder
edits) and [0037](0037-domain-read-model-served-by-graphql.md) decision 4 (a compute over a request body
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
