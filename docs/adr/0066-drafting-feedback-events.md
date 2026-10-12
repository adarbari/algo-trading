# ADR 0066: Drafting feedback events

**Status:** accepted (2026-10-11; design: the architect's plan for Describe-it PR 6, owner decision
2026-10-11 on the admin policy below). Amends [0005](0005-ingestion-is-the-only-writer.md) (the
API's sixth write, after [0058](0058-llm-usage-log-prices-and-budget.md)'s usage log); extends
[0041](0041-natural-language-screener-drafts.md) and [0007](0007-point-in-time-data.md) (the
table's columns). Plan: `docs/drafting/describe-it-plan.md`. Code:
`src/algotrade/services/feedback/`, `src/algotrade/storage/tables/feedback_writer.py`,
`src/algotrade/data/feedback/`, `src/algotrade/services/read/ops/feedback.py`,
`apps/api/algotrade_api/feedback.py`.

## Context
Describe it turns a sentence into a draft screen. Whether it understood is known only by what the
trader did next: saved the draft as it came, edited it, or walked away. The golden set (replayed
in CI to score the prompt, `services/drafting/golden.py`) should come from that real iteration, not
from cases invented at a desk. The usage log (0058) records model calls and cannot say what the
trader made of the answer, and a sentence is personal data that deserves its own rules.

## Decision

### One row per event, `feedback/drafting_events`
Events: `draft_requested`, `draft_returned`, `choice_made`, `formula_accepted`, `formula_skipped`,
`draft_saved`, `screen_finalised`, `edge_revised`. This PR emits the first two and the two save
events, all server side; the choice and formula events are defined now and sent by the browser in
the save body in a later PR (no browser event endpoint exists). Columns: the point-in-time ones of
ADR 0007 (`ts` = the event, `session_date` = its **exchange calendar date**, `knowledge_ts` = `ts`,
`source` = `drafting_feedback`, `run_id`) and `event_id`, `draft_session_id`, `user`, `doc_kind`
(`screen` | `edge`), `doc_id`, `event`, `call_ids` (comma-delimited `usage/llm_calls.call_id`),
`catalogue_version` (a hash of the sorted catalogue names), `prompt_version`, `draft_hash` (the
draft the model returned), `saved_hash`, `sentence` (<= 1,000 characters) and `payload` (a small JSON
string, replaced by a valid "truncated" object past 32,000 characters; see the amendment below). Nullable apart from the event's
identity; older partitions read missing columns as null (the usage log's lesson, 0058). Runs merge;
the key is `draft_session_id, event_id, event`, so two events of one session never collapse and one
event submitted twice is one row.

### Edits are derived, not logged
The draft route returns a new `draft_session_id` (an optional response field). The API remembers the
last draft returned per session in a bounded in-process LRU; the save (`PUT .../draft`, optional
`draft_session_id` in the body) and `POST .../finalise` (optional body, the same field) are diffed on
the server against it: criteria added, removed and changed (`id`, `field`, `op`, `value`) and a changed
tie-break, in the payload. A save with no session id (a hand-built screen) records nothing; one whose
draft this process no longer remembers records `draft_unknown`; a session id is honoured only for the
user and screen it was issued to. An autosave of an unchanged draft is recorded once. `draft_saved`
carries the content hash of the stored draft, `screen_finalised` `Finalised.hash`; both carry the
returned draft's hash, so "saved unchanged" is `draft_hash` equal to the content hash in the payload.
Events are written **only after the config write succeeded**.

### The write
The API's sixth write: `FeedbackWriter` writes only `feedback/*`, only the feedback recorder imports it
(import-linter), `services/feedback` imports no market-data writer and no jobs, and `services/drafting`
imports neither the writer nor the feedback package: the route layer injects the sink
(`create_app(feedback=...)`, a sink that records nothing in tests). The recorder is `BatchRecorder`
(0058, 0028): a bounded queue, one thread, one atomic run per batch (0022). **A dropped event never fails
a request**: a full queue drops the row (logged), a failing write drops the batch (logged), and every
emission swallows its own exception.

### Reads and privacy
`data/feedback` reads the table over a date range (session-free, like the usage read) and only the
read model's loader may import it (import-linter). `load_drafting_events(ctx, viewer, since, limit)`
returns a trader **only their own rows**; an admin reads all rows; the role is the registry's
(`Viewer.role`, ADR 0040), never the client's. **Policy (owner, 2026-10-11): an admin also sees the
formulas and screens traders accepted, across users.** No GraphQL field exists yet; the Admin page
that shows these rows comes with the golden pipeline.

### Retention
The raw sentence and the payload are kept 12 months and then nulled unless the row was curated into
the golden set (`tests/fixtures/drafting/golden/`). The repository is public, so a curated case is
never the trader's text: the owner rewrites it (every sentence of the chain paraphrased) and checks
its criteria for personal specifics (holdings, named positions) before it enters the repository. The nulling and an owner-run erase command for one user are a later change (an
owner-run command in the ingestion CLI, as every rewrite of stored data is); until then the rows are
append-only and `docs/hosting.md`'s store backups apply.

## Amendment (2026-10-11): the whole iteration of a screen

The first cut recorded a diff per draft, so the final criteria and the chain of descriptions could
not be read back. Owner requirement (2026-10-12): for an original sentence, the golden case is the
final criteria the user ended up with after editing the filter; if they change the description
several times, all of the descriptions are stored.

- **A session is one screen's iteration.** `POST .../draft-from-text` takes an optional
  `draft_session_id`: the previous answer's. The API continues that session when the id is the same
  user's, for the same screener, and the screen was not finalised since (`DraftMemory`); an unknown,
  foreign, other-screen or finalised id starts a new session. A save does not end the session
  (describe, save, describe, finalise is one session); finalising does, and so does discarding the
  draft in the browser (it drops its id, so the next description starts a new session; the server
  is not told, see the golden case below). `seq` comes from stored state (the last draft
  returned plus one), so a request that failed does not advance it. `seq` (a new nullable `int64`
  column) is the 1-based ordinal of the draft request in its session; save events carry the `seq`
  of the draft they saved. The browser keeps the last id per screener in the Builder and sends it
  with the next sentence, the save and the finalise (the save never carried it before); it clears
  it when the version is written, on discard, or when another screener opens.
- **The criteria in force are stored, not only a diff.** `draft_requested.payload.current_criteria`
  is the Builder's criteria table (with its tie-break / rank) sent with the request: the trader's
  edits between descriptions. `draft_returned.payload.draft_criteria` is the model's criteria after
  validation, with `dropped` (id, field, reason) and `notes`. `draft_saved` and `screen_finalised`
  carry `saved_criteria`, the stored document's criteria table with its tie-break / rank. Each
  snapshot is cut at 8,000 characters of JSON into `{"truncated": true, "chars": n, "head": ...}`
  and the whole payload at 32,000: never a failed request. A diff, the dropped list and the notes
  are each cut at 4,000 characters first, so the `*_criteria` snapshot always survives the cap.
- **A restart does not orphan the chain.** The draft memory is per process and the API restarts on
  every deploy. After one, a request continuing an unknown id starts a new session and a save of an
  unknown id is filed under session `""` (never under an id that is not the user's); both record
  the id the client claimed as `payload.claimed_session_id`. `services/feedback/chains.py` links a
  row to the claimed session only when that session's rows have the same `user` and `doc_id`.
- **Two tabs on one screen**: a tab that holds the session id continues it; a second tab that
  starts with no id opens its own session. A save is diffed and hashed against the draft of the
  session it names, and the last finalise of the screen is the one that counts for its chain.
- **A golden case** is `(all sentences of one session in order, with the criteria in force at each
  (`current_criteria` of its request), the final criteria (`saved_criteria` of the session's last
  `screen_finalised`))`. **Only a session that ends in `screen_finalised` is labelled.** A
  `draft_saved` with no later finalise is a working draft, unlabelled, as is a session never saved:
  the rows cannot tell a discarded screen from one still being worked on, so no claim is made
  from a save alone. A linked chain is ordered by `ts`, not `seq` (which restarts at 1 when a
  restarted session is relinked); `chains.golden_candidates` is the one place this is decided.
  For a curated case `source_event` is the session's final event id. The public-repo paraphrase
  rule applies to every sentence of the chain: the repository is public, so a curated case holds
  paraphrased sentences, never the trader's own words.
- **Personal data in these rows.** Personal: the typed sentences (`sentence`, which may name
  holdings, strategies or people, and the `dropped` reasons that quote them), the user id (`user`),
  and the saved, requested and returned criteria (`*_criteria`), which are the user's strategy.
  Not personal: the event name, `seq`, the hashes, the catalogue and prompt versions, the call ids
  (they point into the usage log, which holds the same text under its own rules), the exchange date
  and the screener id when it is a site preset's. Retention, viewer scoping and the owner's
  erase command apply to all the personal columns, the payload included.

## Amendment (2026-10-11): the missing-feature request log

A draft may say what the sentence asks that no stored field answers (`missing`, ADR 0041
amendment). Those requests are the signal for what to build next, so they are logged and ranked.
Owner policy decided 2026-10-11.

- **A second table, the same writer**: `feedback/feature_requests`, written only through
  `FeedbackWriter` by its own `BatchRecorder` (`services/feedback/request_recorder.py`; never raises,
  drops on a full queue, one atomic run per batch). It is not `usage/*` (the model-call log) and not
  a drafting event (a request is about a feature, not a draft's life). Columns: the point-in-time
  ones of ADR 0007 (`session_date` the exchange day of `ts`, `knowledge_ts` = `ts`, `source`
  `drafting_feedback`, `run_id`) and `ts`, `user`, `ref` (the backlog key, else the new slug: the
  identity), `key` (set for a backlog item), `new_slug` (set for one the backlog does not know),
  `feasibility`, `span`, `closest` (comma-delimited catalogue names), `call_id`,
  `draft_session_id`; all but `ts`, `user`, `ref` nullable for evolution. Key: (`user`, `ref`,
  `session_date`): one row per user, feature and exchange day.
- **Privacy: the span, never the sentence.** The row holds the clipped span (300 characters) the
  request covers, not the trader's sentence, and only when the span is a piece of the sentence
  (ignoring case and whitespace): a span the model invented or paraphrased is stored as null, and
  `ref` is never derived from free text. `null_spans` and `erase_user` (`services/feedback/requests.py`)
  are the retention and erase edits the feedback retention command applies to this table. It is still personal data (a span can name a holding),
  so the read is viewer-scoped and the retention of this ADR applies to `span`.
- **Who sees what.** A trader sees only their own history (`load_my_requests`: per feature, first
  and last asked, times asked) and never a count or trace of another user; this holds for an admin's
  "my requests" too. An admin sees an ordered ranked list across users (`load_ranked_requests`);
  a trader asking for it gets `PermissionDeniedError` before anything is read. The role is the
  registry's (`Viewer.role`).
- **Ranking** (`services/feedback/ranking.py`, pure): the sum over distinct users of
  `exp(-age_days / 60)`, the age from each user's latest request for the feature, times a
  feasibility weight (`ROLLUP_FROM_STORED` 1.0, `NEEDS_SOURCE` 0.5, `UNCLEAR` 0.25); the raw count
  of distinct (user, day) asks breaks ties, then the later last-seen, then the name; a feature the
  backlog has since PROMOTED or set WONT_DO keeps its score but is listed after every OPEN and
  unmapped one. No embeddings:
  a slug is the same feature only when the backlog says so (a key or alias), re-resolved at read
  time, so an alias added by a PR merges the earlier slugs. A slug the backlog does not know is
  shown to admins as unmapped, with the backlog's status (OPEN / PROMOTED / WONT_DO) beside the
  mapped ones.
- **Wiring**: the route layer calls `record_missing(sink, user, draft.missing, ...)` after the draft
  answer (`services/drafting` imports nothing of `services/feedback`); GraphQL and the web come
  later.

**Note (2026-10-11): the route records requests.** `draft-from-text` now calls `record_missing` for the
draft's post-validation `missing` (never the model's raw list) after the feedback events, for the user
the caller whose sentence it was (as the drafting events), through a second sink (`app.state.requests`, the
`feature_requests` recorder started with the app and flushed at shutdown with the others); a raising
or full sink never fails the draft, and a draft with no missing items writes nothing.

## Consequences
- The golden set grows from real sentences, with the model's answer and what the trader kept.
- Personal data is stored: one more reason the read is viewer-scoped and the sentence short.
- The memory is per process (one API process is assumed, as 0058): after a restart a save records no
  diff for a draft made before it.
- Edge revisions (`edge_revised`) are named but emitted nowhere yet.
