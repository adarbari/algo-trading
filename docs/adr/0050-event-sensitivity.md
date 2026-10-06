# ADR 0050: Event sensitivity: what moves a name, what is coming, and who found out

**Status:** accepted (2026-10-06; owner decisions in
[event-sensitivity-plan.md](../event-sensitivity-plan.md) section 8; decision 3 reviewed by
`architect`, reviewed again with the groups before EV2 ships). Extends
[0007](0007-point-in-time-data.md) (backfilled facts of record), [0005](0005-ingestion-is-the-only-writer.md)
(an analyst's findings enter through an ingestion import), [0038](0038-catalogue-named-values.md)
(every per-name statistic is a catalogue feature), [0041](0041-natural-language-screener-drafts.md)
(a third use of the text-model seam) and [0048](0048-macro-series-with-vintages.md) (the FRED
vendor gains release dates). Amends [0029](0029-rule-screener.md) and 0005 when EV8 lands (an admin
writes one site file through the API).

## Context
A short-put or wheel seller needs to know, per name, which kinds of events have moved it in a
big way (its own earnings, a peer's results, a macro release, a rebalance, or nothing on any
calendar) and which of those fall before each candidate expiry. The platform knows the next
earnings date and nothing else about events: no measured reaction, no peers, no macro
calendar, no cause for an unexplained gap. The owner wants the *true drivers* of each name
found, kept current by a periodic analyst pass, stored, and tracked forward in the UI. Two
years of bars and no stored earnings history before 2026-10-02 are too thin to measure
anything, so history is backfilled, which raises a point-in-time question the platform has
not answered: a fact of record stored years after it happened.

## Decision
1. **Event classes** are own scheduled (earnings, ex-dividend, index change), peer scheduled
   (a measured peer's earnings), macro scheduled (FOMC, CPI, employment, PCE, GDP, PPI, retail
   sales, ISM), market structure (expiries, rebalances, splits and special dividends, by the
   exchange calendar and `events/split` / `events/dividend`), unscheduled (a big move with none
   of the above on its reaction session) and factor-dated (a dated occurrence of a driver the
   deep dive recorded). A **big move** is beyond 5% or beyond 2 of the name's own normal days
   (trailing 20-session ATR% as of the session before); both flags are stored. A split day is
   never unscheduled.
2. **Scope.** The study runs for the tier A / B short-put names plus the site list
   `config/site/events/scope.toml` (kind `events`, typed in `config/site/events/scope.py`;
   symbols resolved through `SymbolResolver` each run) plus the references those names map to.
   A leveraged or inverse fund has no events of its own: it **inherits its reference
   instrument's events**, scaled by `leverage`. The link is a catalogue feature
   (`fund_reference@v1.reference_instrument_id`, ADR 0038) computed from the holdings table,
   with a name rule resolved through `SymbolResolver` as the fallback. Scoped names get bars
   and earnings dates from 2018-01-01 (Stooq split-adjusted daily files stored under their own
   `source`; the Nasdaq calendar by past date, SEC 8-K Item 2.02 as the authoritative source
   of the report date and time).
3. **Point in time: one `known_from` date per event row** (the pattern of ADR 0048, which
   separated `vintage_date` from the storage stamp). Every event row (`events/earnings`,
   `events/macro_release`, `events/filing`, `events/attribution`, `events/factor_occurrence`,
   `instruments/factors`) carries `known_from`: the session on which the fact was knowable.
   A row the nightly stores from a calendar gets its snapshot session; a backfilled past
   event gets its event date (an 8-K its acceptance date); a model attribution the session it
   ran; a dossier row the session of its import. `knowledge_ts` stays the storage stamp
   (stamping overwrites it; nothing is keyed on it). **The one read rule**: as of session S the
   data layer serves rows with `known_from <= S`, and a **statistic** as of S uses only events
   whose inputs are complete on or before S (the reaction session for a move, the reaction
   session plus 5 for `revert_rate`, plus 1 for `iv_crush`), with every lookback window
   (ATR baseline, correlation, peer selection) ending at S. Measured peers, factors and
   attributions are therefore hindsight-free by construction: a 2027 dossier is invisible to a
   2025 session. The reaction session comes from the declared report `time` or the 8-K
   acceptance time, never from which day moved more; an unknown time is counted but excluded
   from the multiples (`time_unknown`). Backward statistics use one report per (instrument,
   fiscal quarter): the confirmed row (8-K 2.02, else a backfill source marked reported) wins
   over a calendar forecast, so a rescheduled date does not count twice. The `InstrumentEvents`
   and `EventCalendar` reads state this rule per ADR 0036 and close the deferred "Events point
   in time" roadmap item in EV1.
4. **Tables** (`architecture/tables.toml`, ingestion the only writer, each with its run mode):
   `events/macro_release` (FRED `releases/dates`, past and scheduled, plus the FOMC dates from
   a site file; merge, keyed by release and date), `events/filing` (8-K items by CIK and
   acceptance time; merge), `events/attribution` (instrument, reaction session, cause class,
   cause text, confidence, evidence refs, `source` in `filing` | `model` | `analyst_review`;
   merge, keyed by instrument, session and source), `instruments/factors` (the deep dive's
   drivers per name, with a `status` of `active` | `retired` since merge never deletes; merge)
   and `events/factor_occurrence` (dated occurrences and undated watch items; merge). A read
   takes, per (instrument, session), the attribution of the **highest source, then the
   latest**: `analyst_review` over `filing` over `model`.
5. **Attribution, nightly.** A big move with no calendared event is attributed first from an
   8-K filed on or just before its reaction session (the item code is the cause: 2.02 results,
   1.01 agreement, 5.02 management, 7.01 guidance, 8.01 other events, 2.01 M&A, 4.02
   restatement), then from Massive's news endpoint (fetched only for that session's big
   movers, capped per night) classified through the `TextModel` seam by a new use case
   `services/attributing` into a closed cause taxonomy with a confidence and the quoted
   headline as evidence. This is the first stored model output (ADR 0041 stored only drafts
   and a cache): it is labelled `source = model`, carries its model and prompt version, and the
   `attributing` step is non-critical (ADR 0039). With the LLM off the move stays
   unattributed, never guessed.
6. **The deep dive is a skill, not a job.** `.claude/skills/event-deep-dive`, run by the owner
   in Claude Code weekly or monthly, reads the store through the CLI and the API, investigates
   the unexplained and low-confidence moves, names each name's factors with evidence and
   their next dated occurrences, and writes a reviewed TOML dossier per name under
   `var/dossiers/`. `algotrade-ingest run dossier-import` validates it (ids through
   `SymbolResolver`, dates, the taxonomy) and writes the rows of decision 4 with the import's
   `run_id` and the import session as `known_from`. The skill never writes Parquet (ADR 0005);
   every import is a run, so the dossier's history is kept and the UI shows the review date
   and each attribution's source.
7. **Features and reads.** `event_reaction@v1`, `peer_sensitivity@v1`, `event_calendar@v1` and
   `fund_reference@v1` are feature groups; screener fields are expression features with
   field-guide entries (ADR 0041's fitness test). Peers are **measured**: candidates from the
   same industry, the same sector ETFs and the most correlated names over the 252 sessions
   ending at S, kept when the name moved more than 1.5 normal days on at least 4 of the
   candidate's report days before S. The read model gains `InstrumentEvents` (history with
   attributions and their sources, drivers, the next 90 days, the 7-90 DTE expiry ladder,
   chart markers) and `EventCalendar` (cross-name), served by GraphQL (ADR 0037).

Rejected: two point-in-time rules (event dates for backward-looking statistics, the storage
stamp for forward-looking facts): peers, factors and attributions are chosen afterwards, so
"the event was public on its date" does not make a statistic about it hindsight-free, and the
storage stamp is overwritten by stamping; same-industry peers by assumption (keeps names that
never move the name, misses cross-industry drivers); headlines for every name every night (5
requests a minute on the free tier; the big movers are the ones that need a cause); the deep
dive as a nightly LLM job (the drivers of a name are analyst judgement with evidence, reviewed
in a diff, not a prompt's output stored unseen); the skill writing tables directly (ADR 0005);
hiding backfilled events behind the storage stamp for history too (every statistic would be
UNKNOWN until 2027).

## Consequences
- `known_from` joins `session_date`, `knowledge_ts`, `source` and `run_id` as a point-in-time
  column of event rows; the data layer filters on it, and the `architect` review before EV2
  confirms the groups' "inputs complete on or before S" windows and the backtest path.
- The owner has recurring work: run the backfills once, the deep dive weekly or monthly, and
  review each dossier diff; a name unreviewed for 90 days is flagged on the Admin screen.
- A new vendor use (Massive news), a new SEC reader (8-K index) and a new FRED endpoint
  (release dates), each on a source already in `libs/sources`; no new vendor.
- The scope file is edited by PR until EV8 gives Admin a write for it (amending ADRs 0005 and
  0029 then: an admin writes one site file through the API).
- Reviewed 2026-10-06 by `architect`: the original two-rule design was replaced by this
  decision 3 (hindsight in measured peers and dossiers, statistics with inputs after S, the
  storage stamp as a key, rescheduled dates counted twice, Stooq split days, run modes).
