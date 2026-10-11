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
string, replaced by a valid "clipped" object past 4,000 characters). Nullable apart from the event's
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
The raw `sentence` and the `payload` are kept 12 months and then nulled unless the row is **curated**.
A row is curated when its `event_id` is listed in the `source_event` field of a golden case
(`tests/fixtures/drafting/golden/`); no column marks it. The later owner-run `feedback retain` command
reads those ids and nulls the rest. **The retain command and an erase command (all rows of one user)
are later PRs; until they exist nothing is nulled or erased and the rows are append-only.** Erasure
must also cover `usage/llm_calls` failure rows (they hold the prompt, hence the sentence: the
`sentence` / `answer` columns of ADR 0058's 2026-10-11 amendment) and the store backups
(`docs/hosting.md`).

### Golden cases and the public repository
The repository is public. A golden case built from a real trader's sentence is **never copied verbatim
into git**: `golden curate` requires the owner's paraphrase or redaction of the sentence, and
`golden candidates` prints sentences only to the owner's terminal.

### Who edited
Rows are filed under the user whose screen it is; when an admin acts for a trader (`X-Act-For`) the
save events carry the caller in the payload (`actor`). The save and finalise rows carry no sentence (the
`draft_returned` row holds it once). A save of a draft this process does not remember is recorded once
per (session, user, content).

## Consequences
- The golden set grows from real sentences, with the model's answer and what the trader kept.
- Personal data is stored: one more reason the read is viewer-scoped and the sentence short.
- The memory is per process (one API process is assumed, as 0058): after a restart a save records no
  diff for a draft made before it.
- Edge revisions (`edge_revised`) are named but emitted nowhere yet.
