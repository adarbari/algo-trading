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
`reasoning_effort = low`; (7) result cache. Measured through `usage/llm_calls` (cache tokens, call id,
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

Golden pipeline: an owner-run `golden candidates` builds cases (sentence, catalogue version, final saved
criteria): saved unchanged is a positive, saved with edits a correction, abandoned unlabelled;
`golden curate` writes accepted cases to `tests/fixtures/drafting/golden/` with recorded answers per model
for CI replay, scored structurally (fields, operators, thresholds within a tolerance). Anti-leak: train /
held-out split; train cases may grow the phrasebook; a fitness test fails if a held-out sentence appears in
prompt examples or the phrasebook; the prompt never picks examples automatically. Anti-bias: per-user caps,
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

## PR order

0. Done: #514 failure log (rejected rows, error / stage / sentence / answer on the admin usage page).
1. Meter fix: cache read / write tokens, `call_id`, `prompt_version`, `stage` on `usage/llm_calls`
   (ADR 0058 amendment; the CLI adapter drops cache tokens today, so input is under-reported ~10^5).
2. Prompt reorder for a stable prefix; the guide trimmed to its criterion lines.
3. Retrieval slice, phrasebook skip-the-model and the golden replay harness (architect review: a missed
   field must not turn into a false "missing").
4. Cheap-model-first tiering, the repair retry, fall-through on invalid output, schema-constrained JSON.
5. The A / B / C contract: parsing, validation, dry run, fingerprint, `feature_backlog.toml` (ADR 0041
   amendment).
6. New ADR and `feedback/drafting_events` recorder; `usage/feature_requests`.
7. Builder panel, formula flow and Guide entries; choices carried in the save body; server-side diff.
8. Admin: feature requests and accepted formulas; `golden candidates` / `curate`; the leak test;
   `promote-feature` skill. Later: "Notify me when available".

PRs 1 and 6 touch `usage.py` and the ledger that #514 changed: start after #514 merges.

## Risks

Retrieval misses showing as false "missing" (keep the full field index in the prefix; replay test);
a user-specific prefix defeating the cache (caller's features last); sentences are personal data;
a full recorder queue drops events (acceptable, disclosed); the Claude CLI serialises calls (one lock);
vague words ("majority", "recent") silently hardened into numbers (shown as choices, never silent).
