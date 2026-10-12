# Describe it: reliable, cheap, learning (plan)

Status: plan, 2026-10-11 (owner decisions in this session; designs by an Opus architect review and a Fable
outside-research pass). Extends ADR 0041 (text-model drafting), ADR 0058 (usage ledger), ADR 0023
(feature store), ADR 0053 (edges). Nothing here is built except PR #514 (failure log, see "Done").

## Why

A trader's sentence ("liquid optionable stocks over $5 within 5% of their 52-week high that held within
support lines for two years") went to the model and failed with "the model's answer is not JSON". Three
things were wrong: the answer was not kept, so we could not tell why; a call sends ~110k tokens
(field guide ~83k, catalogue ~18k, phrasebook ~6k; measured 2026-10-11) and costs ~$0.70 notional and
~20 s on Sonnet; and a request the catalogue cannot express ends as a lost error, not as information.

## The answer: A / B / C plus choices

One JSON object, additive over today's `{criteria, tie_break, notes}`:

- `criteria` (A): criteria over existing catalogue fields, as today.
- `formulas` (B1): a missing concept buildable as a same-session expression over existing features
  (`features/expressions/`: per-row maths, no lag, window or rolling). Each carries `name` (`draft_`
  prefix), `expr`, `dtype`, `unit`, `description`, `null_meaning`, `inputs`, and the `criterion` that uses
  it. The server type-checks it (`FeatureSet.with_user`) and dry-runs it on the latest session (null rate,
  range, sample rows) before it is offered. A criterion on a formula stays pending until the trader accepts.
- `missing` (B2 / C): `{key, new_key_slug?, span, description, why_needed, closest, feasibility}` with
  `feasibility` in `ROLLUP_FROM_STORED` (a time-window rollup in code over stored data, B2), `NEEDS_SOURCE`
  (new data, C), `UNCLEAR`. `key` is one of the open backlog keys given in the prompt, else null with a slug.
- `unresolved`: an ambiguous term ("liquid", "majority") with 2-3 alternatives, each carrying its own ready
  criterion, so the trader's pick swaps locally with no second model call.

Never auto-applied: B and C are shown, and a formula becomes a feature only when the trader accepts it.

## Features and duplicates

- A trader's accepted formula is saved through `save_user_feature` as their own feature
  (`config/users/<id>/features/`), private, usable at once.
- Admins see accepted formulas across users (owner decision 2026-10-11; a policy note for ADR 0015/0029).
  Traders see only their own data, including their own missing-feature requests, never counts from others.
- Promotion to a site feature is a PR through `add-feature` (`config/site/features/`), carrying the
  catalogue (`make features-doc`), field guide, phrasebook and Guide entries; the Guide coverage checks
  make a missing entry fail CI. A `promote-feature` skill drafts that PR from a backlog item.
- Duplicates: the server normalises each formula (qualified names, constants folded, commutative order)
  and hashes it. A fingerprint equal to a site or the trader's own feature drops the proposal and the
  draft uses the existing field. The admin backlog groups accepted formulas by fingerprint. Structurally
  different equivalents are merged by an admin by hand.
- Missing features: a curated list `config/site/feature_backlog.toml` (key, description, feasibility,
  aliases, status OPEN / PROMOTED / WONT_DO, promoted_to; PR only) and a request log table
  `usage/feature_requests` (user, key or slug, feasibility, span; the span, not the sentence). Rank =
  sum over distinct users of exp(-age/60 d) x feasibility weight (1.0 / 0.5 / 0.25), one count per
  (user, key, day). No embeddings at first. "Notify me when available" is a later, lower-priority item.

## Reliability

Schema-constrained JSON where the provider supports it (Gemini and OpenAI-style `response_format`; the
Claude CLI `--json-schema`) plus local validation and one repair retry that feeds the error back; a
non-valid answer falls through to the next provider (today only "unavailable" does). Known phrases resolve
in code (phrasebook, field guide) before the model; thresholds come from the field guide, never from the
model's memory; code verifies fields, types, dry-runs and fingerprints. Cache by normalised sentence,
current criteria, catalogue version, prompt version and model. Model versions are pinned.
Measured live, by the owner only (CI never calls a model): `algotrade-api golden run [--cases ID,...]
[--split train|held_out|all] [--provider ID ...] [--repeat 3] [--record] [--json] --yes` runs the real
`draft_screen` over the golden cases per provider and reports pass rate, consistency, invalid rate, tokens,
cache, latency and cost, under `--max-calls` / `--budget-usd` caps (`src/algotrade/services/drafting/golden_run.py`).
It also reports the criteria the server dropped (`drops_total`, `invented_field_drops` with the invented names, `would_repair`; `--json` lists each repeat's drops) and paces a rate-limited free tier (`--pace`, `--batch N --batch-pause S`; a 429 waits and retries twice).

## Token and latency budget

Targets for a first call on a cheap model (Haiku or Gemini Flash): input <= 12k tokens (>= 50% cache read),
output <= 700, cost <= $0.015, latency p50 <= 4 s, p90 <= 10 s; escalated to Sonnet <= $0.06, p90 <= 20 s.
Levers by saving: (1) a retrieval slice: a stable prefix (task, grammar, examples ~1.4k; a compact index of
all fields `name|type|unit` ~4-5k) plus a per-sentence slice of ~25 fields (catalogue line, the field
guide's "criterion per intent" only, matched phrasebook entries; chosen by deterministic phrasebook / name /
description match plus ~15 always-included core fields) = 9-12k tokens; (2) prompt order for a stable cached
prefix: static text, site catalogue index, variable slice, the caller's own features, the sentence;
(3) skip the model when the phrasebook resolves every clause; (4) cheap model first, escalate on invalid
output after the repair, not on missing or unresolved items; (5) two phases: a local `draft-resolve` returns
the A rows and alternatives at once, then the model call; (6) caps: compact keys, ~800 answer tokens,
`reasoning_effort = low`; (7) result cache (none for drafting today: `TextCache` serves only explaining; not added by PR 3). Measured through `usage/llm_calls` (cache tokens, call id,
prompt version, stage first / repair / escalate).

## Learning from iteration (golden set)

Table `feedback/drafting_events` (new ADR; the API's sixth write; recorder in `services/feedback/`, not in
`services/drafting/`): one row per event (`draft_requested`, `draft_returned`, `choice_made`,
`formula_accepted`, `formula_skipped`, `draft_saved`, `screen_finalised`, `edge_revised`) with
`draft_session_id`, user, `doc_kind` / `doc_id`, `call_ids`, catalogue and prompt versions, `draft_hash`,
`saved_hash`, the sentence (<= 1000 chars) and a small payload. Edits are derived, not logged: at save the
server diffs the last returned draft against the saved document; choices and skips travel in the save
request body. Written only after the config write succeeded; a dropped event never fails a save. Traders
see only their own rows. Raw sentences are kept 12 months, then nulled unless curated.

A session is one screen's iteration (ADR 0066, amendment 2026-10-11): successive descriptions of the
same screen share a `draft_session_id` until it is finalised or discarded, each draft request has its `seq`, and the
events carry the criteria in force (`current_criteria` on a request: the trader's edits between
descriptions; `draft_criteria` on a return; `saved_criteria` on a save). A **golden case** is
`(all sentences of one session in order by `ts`, with the criteria in force at each, the final
criteria = `saved_criteria` of its `screen_finalised`)`; only a session with a `screen_finalised` is
labelled: saved-only, discarded (not detectable from the rows) and never-saved sessions are
unlabelled (`chains.golden_candidates`); `source_event` of a curated case is
the session's final event id; the public-repo paraphrase rule applies to every sentence of the chain.

Golden pipeline: an owner-run `golden candidates` builds cases (sentence, catalogue version, final
criteria): finalised unchanged is a positive, finalised with edits a correction, anything else unlabelled;
`golden curate` writes accepted cases to `tests/fixtures/drafting/golden/` with recorded answers per model
for CI replay, scored structurally (fields, operators, thresholds within a tolerance). Anti-leak: train /
held-out split; train cases may grow the phrasebook; a fitness test fails if a held-out sentence appears in
prompt examples or the phrasebook; the prompt never picks examples automatically. Anti-bias: per-user caps,
Built (PR 8, `services/feedback/{candidates,curate}.py`): `algotrade-api golden candidates [--since --user --limit --json]` lists
sampled finalised sessions (real sentences, owner's terminal only; per-user monthly cap, near-duplicates out, stratified by
feature group, holdings flagged) and `golden curate --from curation.json [--dry-run] [--yes]` writes cases from the owner's
paraphrases (verbatim guard against every loaded sentence incl. 5-word runs, criteria validated, holding-like tokens warn only, ~20% held out by hash, never overwrites, case carries `source_events` for retention and `recorded: false` until `golden run --record`, 14-day fitness limit); both refuse a capped (500-event) read.
near-duplicate removal, stratified sampling, a coverage report.

## Web

Describe it stays the panel at the top of the Builder; the draft loads into the criteria list at once
(A live, B as a ghost row "waiting on formula", unresolved on the model's default). A review panel under
the input explains what was understood: the sentence tagged applied / formula / needs your call / not
available yet, a formula card with its dry run and Review and add / Skip, a "requested, not applied" card
for C showing only the trader's own history, and choices that swap criteria locally. Finalize blocks on
pending formulas, not on missing features (the gap is saved in the screen's notes). Failure states: a
trader-facing message with Try again; a visible waiting phase with Cancel. Every new term (buckets,
statuses, pending formula, needs your call) ships its Guide entry in the same PR.

## PR order (state 2026-10-12)

Done: #514 failure log; #521 usage meter (cache tokens, call ids); #522 stable prefix; #526 golden replay
harness; #528 answer schema, repair, fall-through; #529 retrieval slice; #530 + #533 feedback events (one
session per screen, the iteration chain); #531 live golden run command; #535 A / B / C contract; #523
fingerprint and dry-run; #524 design-system components; #525 backlog config; #537 golden candidates and
curate; #539 request log and ranking; #538 review-and-release; #536 promote-feature skill.
Phrasebook structured thresholds (`[[phrase.criterion]]`, `resolves_fully` in `services/drafting/phrasebook`,
`PROMPT_VERSION` 4) are built but unwired; wiring lever 3 into `draft_screen` is next.

In flight: #540 feedback retention / erase.

Not started (owner in brackets):
- Request-log route wiring, after #535 (implementer, API).
- Builder panel wiring, PR 7 (implementer, web), then the admin accepted-formula list.
- Admin feature-requests page, PR 8 (implementer, web).
- Prompt headroom: a token-budgeted slice and a compact index; the largest golden prompt margin is about 77
  tokens (architect decides, implementer builds).
- `services/drafting` folder split (`contract/`, `golden/`) (implementer).
- Structured phrasebook thresholds, then the skip-the-model short-cut (architect, then implementer).
- Enum values for index-only fields: measure after the live golden run (owner question).
- The live golden run: approved by the owner, Gemini first, $3 cap, `--yes` (owner runs it).
- "Notify me when available" (lowest priority); `edge_revised` event (reserved, only if a save route exists).

Follow-up (owner question, not built): should index-only fields show their enum values? The model otherwise
guesses a value and the validator drops a wrong guess; adding them to the prefix would exceed the 15k budget at
the largest case, so measure it in the live golden run first.

## Risks

Retrieval misses showing as false "missing" (keep the full field index in the prefix; replay test);
a user-specific prefix defeating the cache (caller's features last); sentences are personal data;
a full recorder queue drops events (acceptable, disclosed); the Claude CLI serialises calls (one lock);
vague words ("majority", "recent") silently hardened into numbers (shown as choices, never silent).
