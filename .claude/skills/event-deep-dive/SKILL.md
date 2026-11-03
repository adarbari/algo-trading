---
name: event-deep-dive
description: The owner-run deep dive on one or more names (ADR 0050 decision 6; plan section 4.6) - find what truly drives a name (its factors, their next dated occurrences, the real cause of its unexplained big moves), write a reviewed dossier TOML, and import it with `algotrade-ingest run dossier-import`. Use weekly or monthly on the event-study scope list, or when asked to review why a name moves.
---

# Event deep dive

Analyst work, not a nightly formula: for MU the drivers are DRAM / HBM pricing and the Korean
memory makers' results; for MRNA, HHS policy and FDA dates; for MSTR, Bitcoin and its financing.
The skill finds them, you review them, **ingestion stays the only writer** (CLAUDE.md "Event
sensitivity"): never touch Parquet, only write the dossier file and run the import.
Format: `dossier-format.md` next to this file. The ADR: `docs/adr/0050-event-sensitivity.md`.

Run it on one name, a list, or the scope list (`config/site/events/scope.toml`). One name at a
time, in order; stop at any step that has nothing to say.

1. **Read the store (through the API, never the files).** Start `algotrade-api` locally (or use the
   hosted one) and query GraphQL for the name: `instrument(id) { events(kinds: ["attribution"]) {...}
   eventStudy { ahead filings ladder } }` (schema `apps/api/schema.graphql`; the event study's
   per-type multiples come with `features(names: [...])` of the `event_reaction@v1` group). Get:
   the 20 largest moves of the lookback (`big_move_*` rows) with their current attribution and its
   source, the study table, the peers, the open 8-Ks, the previous dossier (`var/dossiers/<ticker>/`).
2. **Investigate the unexplained and low-confidence moves** (a `filing` row under 0.8 confidence, a
   `model` row, or none): web, filings, transcripts. Decide the cause of each from the closed
   taxonomy (`CAUSES`); if none fits honestly use `other`. Cite what you read in `evidence`.
3. **Name the factors**: each driver of the name's moves with a kind, a one-paragraph description,
   the past instances it explains (`occurrence`, dated) and its **next** dated occurrences; an
   undated one is a `watch` with an expected window. Retire a factor that stopped driving it
   (`status = "retired"`), never delete it. Date only what a source gives; no guesses.
4. **Write the dossier** `var/dossiers/<ticker>/<today>.toml` (copy the previous file and edit, so
   the diff shows what changed). Show the owner the diff and wait for their review: the import is
   the point where it becomes data.
5. **Import** after the owner's yes:

   ```bash
   algotrade-ingest run dossier-import --path var/dossiers/MU/2026-11-03.toml
   ```

   `--path` is a file or a folder (one import for every `*.toml` below it); `--date` defaults to the
   last session and becomes every row's `known_from`. A validation error lists every problem and
   stores nothing: fix the file and rerun.
6. **Report** what changed: moves newly explained, factors added or retired, dates added, and the
   names whose last review is older than 90 days.

Rules: no trade recommendation or direction forecast (plan non-goals); a fact you cannot source is
left out, not guessed; the text model is not involved here (the owner's own Claude login runs this).
