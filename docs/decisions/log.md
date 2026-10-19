# Decision log

Append-only, newest last: an entry is never edited except its `status` line (and the
`- confirmed:` line added with it); a reversal is a new entry. A unit test cannot check that a
diff touched only status lines, so a reviewer does. One entry per policy decision, or design
call worth a line, whoever took it (`.claude/skills/review-and-release`, section 2).
`decided by`: owner | Fable on the owner's behalf | orchestrator (design call). The
orchestrator never decides policy (who sees what, stored personal data, retention, money,
product behaviour, an ADR contradiction); a heuristic test rejects `orchestrator` on an entry
about those topics.
`status`: final | pending owner confirmation | overruled. `final` needs `decided by: owner` or
a `- confirmed: owner YYYY-MM-DD` line: only the owner's word makes an entry final. The owner
confirms or overrules by telling the session, which updates the entry (an overrule means a
follow-up PR).

## 2026-10-11 | Harness | Release without owner review
- Question: does a PR with no product or policy change wait for the owner after review?
- Options: wait for the owner / release after the Opus reviewer's `Re-review: no` and green CI.
- Decision: no owner review needed for PRs without product or policy change.
- decided by: owner
- status: final
- Reasoning: the reviewer and CI are the gate; the owner's time goes to policy only.

## 2026-10-11 | PR #528 (Describe it) | Repair is best-effort
- Question: must the one repair attempt always run?
- Options: always run / skip when it would eat the later providers' reserved time.
- Decision: best-effort: skipped when it would consume the later providers' reserved time.
- decided by: Fable on the owner's behalf
- status: pending owner confirmation
- Reasoning: a fallback provider answering beats a repaired answer from a slower one.

## 2026-10-11 | Describe it golden run | Score the first answer only
- Question: does the golden run score the first answer or the repaired one?
- Options: first answer / best of first and repair.
- Decision: the first answer only.
- decided by: Fable on the owner's behalf
- status: pending owner confirmation
- Reasoning: scoring repairs hides prompt weakness and inflates the measured pass rate.

## 2026-10-11 | Describe it retrieval | synonyms.py deleted
- Question: keep `synonyms.py` in retrieval?
- Options: keep / delete.
- Decision: deleted.
- decided by: Fable on the owner's behalf
- status: pending owner confirmation
- Reasoning: synonyms tuned on golden phrasing risk a leaked train/test split.

## 2026-10-11 | Describe it feedback (ADR 0066) | Which sessions are golden candidates
- Question: is a save without a finalise a golden candidate?
- Options: any saved session / only sessions that end in a finalise.
- Decision: only sessions ending in a finalise are candidates; a save without finalise is unlabelled.
- decided by: Fable on the owner's behalf
- status: pending owner confirmation
- Reasoning: only a finalise records the criteria the user accepted as right.

## 2026-10-11 | Describe it feedback | Admins see all sentences and accepted formulas
- Question: who sees users' sentences and accepted formulas?
- Options: own only / admins see all.
- Decision: admins see all users' sentences and accepted formulas.
- decided by: owner
- status: final
- Reasoning: admins tune the prompt from real usage.

## 2026-10-11 | Describe it feedback | Raw sentence retention
- Question: how long are raw sentences kept?
- Options: shorter / 12 months / indefinitely.
- Decision: 12 months.
- decided by: owner
- status: final
- Reasoning: enough history to evaluate prompts without keeping personal text forever.

## 2026-10-11 | Describe it golden set | Cases are paraphrased, never copied
- Question: may user sentences enter the public repo as golden cases?
- Options: verbatim / paraphrased by the owner.
- Decision: the owner paraphrases each case; none is copied verbatim into the public repo.
- decided by: owner
- status: final
- Reasoning: the repo is public and sentences are user data.

## 2026-10-11 | Describe it golden run | Live run budget
- Question: cap on the live golden run's spend?
- Options: no cap / $3 USD.
- Decision: capped at $3 USD.
- decided by: owner
- status: final
- Reasoning: a bounded cost for a run that calls paid providers.

## 2026-10-11 | Local LLM chain | Gemini first for testing
- Question: which provider leads the local chain while testing?
- Options: any order / Gemini first.
- Decision: Gemini first in the local LLM chain.
- decided by: owner
- status: final
- Reasoning: free tier suits testing.

## 2026-10-11 | Describe it feedback | Missing-feature history visibility
- Question: what do traders see of missing-feature requests?
- Options: own history / counts across users.
- Decision: traders see only their own missing-feature history, never counts from others.
- decided by: owner
- status: final
- Reasoning: other users' activity is not shown to traders.

## 2026-10-11 | Describe it feedback | "Notify me when available" priority
- Question: build order for "Notify me when available"?
- Options: with the other feedback features / later.
- Decision: lower priority than the other features.
- decided by: owner
- status: final
- Reasoning: it needs a notification channel the other features do not.

## 2026-10-11 | PR #537 golden curate | Sentence still names a holding
- Question: what happens when a paraphrased sentence still looks like it names a holding?
- Options: refuse unless allowed / warn only / always refuse.
- Decision: warn loudly, listing the tokens, and still write the case.
- decided by: owner
- status: final
- Reasoning: the owner chose warn-only in the session.

## 2026-10-11 | PR #537 golden curate | Unrecorded curated cases
- Question: may a curated case with no recorded answer stay in the set?
- Options: fail CI at once / skip forever / skip for 14 days then fail.
- Decision: the replay test skips a case with `recorded: false`; `make status` warns after 14 days (no CI failure); a fitness test bounds the state structurally. (Wording corrected 2026-10-11 to the owner-confirmed behaviour: warn only.)
- decided by: owner (confirmed 2026-10-11)
- proposed by: orchestrator, applied while the owner was away
- status: final
- Reasoning: CI must not go red on the PR that adds a curated case, but cases must not stay unrecorded.

## 2026-10-11 | PR #535 | Prompt budget
- Question: how does the drafting prompt stay inside its token budget?
- Options: shorten field-detail descriptions / cap backlog keys and shorten examples.
- Decision: field-detail descriptions stay at 160 chars (restored); open backlog keys in the prompt are capped at 8, relevance first; the second worked example is shortened; the budget test pads the keys to the cap. The margin is about 77 tokens, so a retrieval trim PR comes before any further prompt text.
- decided by: orchestrator (design call)
- status: pending owner confirmation
- Reasoning: taken following two Opus reviews.

## 2026-10-11 | PR #535 | Split services/drafting
- Question: when is the full `services/drafting` folder (9 of 10 modules) split?
- Options: inside #535 / a separate refactor PR after #535 merges.
- Decision: split into `contract/` and `golden/` subfolders in a separate refactor PR after #535 merges.
- decided by: orchestrator (design call)
- status: pending owner confirmation
- Reasoning: keeps #535 reviewable.

## 2026-10-11 | PR #540 | Retention of curated golden cases
- Question: which events does a curated golden case spare from retention?
- Options: only its final event / the whole chain.
- Decision: a curated golden case spares the whole chain (every event id in `source_events`), not only its final event.
- decided by: owner (confirmed 2026-10-11)
- proposed by: orchestrator, applied while the owner was away
- status: final
- Reasoning: the stored iteration stays whole.

## 2026-10-11 | PR #535 | API shape of the formula dry run
- Question: what does REST serve of `FormulaDryRun`, and which type is `Alternative.label`?
- Options: serve `missing` / withhold it; `label` as enum / text.
- Decision: `FormulaDryRun.missing` is not served over REST; `Alternative.label` is `text` in the API.
- decided by: owner (confirmed 2026-10-11)
- proposed by: orchestrator, applied while the owner was away
- status: final
- Reasoning: `missing` listed table names, an admin-only cause under ADR 0056, and label follows ADR 0038.

## 2026-10-11 | Feature-request ranked list | PROMOTED and WONT_DO keys
- Question: are PROMOTED and WONT_DO keys shown in the ranked list?
- Options: keep, sorted last / hide.
- Decision: they stay visible, sorted last with their status.
- decided by: owner
- status: final
- Reasoning: traders see what was decided, not only what is open.

## 2026-10-11 | Request log | Span cap
- Question: how much of the sentence does the request log keep?
- Options: 120 chars / 300 chars / key only.
- Decision: 300 characters, a substring of the sentence.
- decided by: owner
- status: final
- Reasoning: enough context to judge a request without storing whole sentences.

## 2026-10-11 | Harness | Who decides what
- Question: what may the orchestrating session decide, and what goes to the owner or Fable?
- Options: the orchestrator decides everything not marked policy / design calls only.
- Decision: the orchestrating session decides design and engineering calls only (thresholds, test structure, refactor order). Every policy item (who sees what, stored personal data, retention and erasure, money or budget, product behaviour or scope, ADR contradictions) goes to the owner in the session, else to a Fable agent. Fable may not decide spend above caps, deleting or erasing data, security or permission settings, publishing outside the repo, merging with failing CI, or overriding an ADR: those go to the owner only.
- decided by: owner
- status: final
- Reasoning: policy and money are the owner's; the orchestrator's tier is design.

## 2026-10-11 | Harness | Confirmation of three orchestrator-logged entries
- Question: do the owner's confirmations stand for "Unrecorded curated cases", "Retention of curated golden cases" and "API shape of the formula dry run"?
- Options: confirm / overrule.
- Decision: confirmed: curated cases spare the whole chain from retention; unrecorded curated cases only warn after 14 days; the draft API does not serve the formula dry run's table names. All three are `final`.
- decided by: owner
- status: final
- Reasoning: they were taken by the orchestrator, which may not decide policy; the owner confirmed them in the session.

## 2026-10-11 | PR 7 Builder draft review | Screen notes key
- Question: where is the gap of a missing feature saved, and does it change the config hash?
- Options: a new optional `notes` list on the rule-screen spec (in the hash) / out of the hash / a separate store.
- Decision: an optional `notes` list (10 items, 200 characters each) on the rule-screen spec; absent it, the canonical form and hash are unchanged; present it, an edit makes a new hash.
- decided by: orchestrator (design call)
- status: pending owner confirmation
- Reasoning: the plan says the gap is saved in the screen's notes; a run should record what the screen did not cover.

## 2026-10-11 | PR 7 Builder draft review | Sentence tags
- Question: the server sends spans only for unresolved terms and missing features; how is the rest of the sentence tagged?
- Options: tag only what the server spans / match criteria to words in the browser / add spans to the answer contract.
- Decision: tag only the server's spans in this PR (needs your call, not available yet); applied and formula spans wait for a contract change.
- decided by: proposed by orchestrator; awaiting owner
- status: pending owner confirmation
- Reasoning: the browser derives nothing (ADR 0038); a contract change is a separate PR.
- note: superseded by the explained-parts decision (2026-10-11, below); the tagged sentence is not built.

## 2026-10-11 | Describe it review | Explained parts
- Question: how does the review show what the model understood of the sentence?
- Options: the tagged sentence only / tags plus part cards / the sentence quoted inside each part
- Decision: instead of the verbatim tagged sentence, the review shows explained parts: for every part, the trader's quoted words, then "We read this as...", then that part's criteria, formula, readings and suggestions.
- decided by: owner
- status: final
- Reasoning: the trader checks each reading against their own words (answered in the session).

## 2026-10-11 | Describe it review | Fixing one part
- Question: how does a trader fix one part of a draft?
- Options: edit only / retype only / both
- Decision: both ways: pick another reading or edit rows (instant, no model call), or retype just that part's words and re-draft only that part (one scoped model call).
- decided by: owner
- status: final
- Reasoning: cheap local fixes first; a model call only when the words change.

## 2026-10-11 | Describe it review | Quoted words and not understood
- Question: is there a separate tagged sentence line, and where do unplaced words go?
- Options: a separate line / the sentence quoted inside each part card
- Decision: the sentence is quoted inside each part card, with no separate tagged line; words the model could not place appear as a "not understood" part.
- decided by: owner
- status: final
- Reasoning: one place to read, and nothing is silently dropped.

## 2026-10-11 | Describe it review | Retyping a hand-edited part
- Question: what happens when the trader retypes a part they hand-edited?
- Options: replace silently / ask first / refuse
- Decision: ask, then replace the part's rows.
- decided by: owner
- status: final
- Reasoning: hand edits are never lost without a confirmation.

## 2026-10-11 | Describe it review | Kept from your screen
- Question: where do criteria tied to none of the sentence's words appear?
- Options: hide them / a separate card
- Decision: in a "Kept from your screen" card.
- decided by: owner
- status: final
- Reasoning: existing criteria stay visible and are not attributed to words they did not come from.

## 2026-10-11 | Describe it part re-draft | Cost control type
- Question: how is the cost of part re-drafts controlled?
- Options: a daily cap per user / a per-session cap / a rate limit
- Decision: a daily cap per user.
- decided by: owner
- status: final
- Reasoning: the owner chose the type of control.

## 2026-10-11 | Describe it part re-draft | Daily cap number
- Question: how many part re-drafts per user per day?
- Options: 10 / 30 / 100
- Decision: 30 per user per day, a second entry in `config/site/llm.toml` (configurable).
- decided by: proposed by orchestrator; awaiting owner
- status: pending owner confirmation
- Reasoning: the design default; the owner chose only the type.

## 2026-10-11 | Describe it feedback | Retention of retyped part words
- Question: how long are the words a trader retypes for a part kept?
- Options: the 12-month sentence rule / a different period
- Decision: the same 12-month rule as sentences.
- decided by: owner
- status: final
- Reasoning: a consequence of the owner's earlier retention decision (Raw sentence retention), logged under that authority.

## 2026-10-11 | Describe it feedback | Admins read edge text
- Question: may admins read edge thesis text and revisions?
- Options: own only / admins see all
- Decision: admins may read edge thesis text and revisions, the same as sentences.
- decided by: owner
- status: final
- Reasoning: admins tune from real usage; same rule as sentences.

## 2026-10-11 | Describe it feedback (ADR 0066) | Erase behaviour
- Question: what does erasing a user's feedback do to linked events?
- Options: delete rows / scrub and unlink
- Decision: scrub and unlink.
- decided by: owner
- status: final
- Reasoning: the personal text goes while the aggregate record stays intact.

## 2026-10-11 | Describe it drafting | Extra protective checks
- Question: how are extra protective checks added to a draft?
- Options: apply silently / suggest only
- Decision: added as soft or score suggestions, never applied silently.
- decided by: owner
- status: final
- Reasoning: the trader decides what enters the screen.

## 2026-10-11 | Describe it review | Items tied to no words
- Question: how does the review show criteria the model tied to no words of the sentence (origin `unplaced`)?
- Options: inside a not-understood card / a separate card
- Decision: the web shows them as a separate card, "Added without your words"; the backend is as built (a catch-all part with no words, origin `unplaced`, apart from `gap` parts, which carry the words nobody covered).
- decided by: owner
- status: final
- Reasoning: owner decision in the session, 2026-10-11 (source: owner); the rows are not the trader's words and are not "not understood".

## 2026-10-12 | Describe it phrasebook shortcut | What a no-model draft carries
- Question: a sentence the structured phrasebook resolves in full is drafted without the model; what does that draft carry beyond the entries' criteria?
- Options: only the entries' criteria / the same `instrument.status` ACTIVE scaffolding a model draft always has; a ledger row for the call / no call id; a reading the server writes / none.
- Decision: the ACTIVE scaffolding is added when no entry says it (shown in the "Added without your words" card, as for a model draft); no call id and no ledger row (the draft cost nothing; `draft_returned.payload.stage` is `phrasebook`); each part carries a server-written reading from its entry's criteria, `reading_source` `server`; a phrase on a field the Builder's current criteria already hold, or any other doubt, goes to the model.
- decided by: orchestrator (design call)
- status: pending owner confirmation
- Reasoning: a no-model draft must match what the same sentence would give from the model (inactive instruments excluded), keep every event written as usual without a call id pointing at nothing, and never guess when the Builder's own criteria are in play.

## 2026-10-12 | Describe it part re-draft | Day of the cap
- Question: which day does the daily cap on part re-drafts count?
- Options: the exchange calendar date (as the usage log partitions) / the trader's local day.
- Decision: the exchange calendar date (America/New_York), as built; the 429 says how many seconds until it turns.
- decided by: owner
- confirmed: owner 2026-10-12
- status: final
- Reasoning: owner answer in the session (PR #561 review); the usage log the count is read from is partitioned that way.

## 2026-10-12 | Describe it part re-draft | What uses up a place
- Question: does a part re-draft that fails use up one of the user's daily places?
- Options: every call asked counts / only a call that returned a draft counts.
- Decision: only a call that returned a draft counts. A failed, invalid or unavailable call gives its place back (the place is reserved under a lock while the call is in flight, released when it raises); the usage log counts only answered calls (more `ok` / `fell_back` attempts than `rejected` rows); the cap still fails closed when the count cannot be read. Changes the first build of PR #561, which counted failed calls.
- decided by: owner
- confirmed: owner 2026-10-12
- status: final
- Reasoning: owner answer in the session (PR #561 review): a trader should not lose a place to the system's failure.

## 2026-10-12 | Describe it drafting | One prompt version for both prompts
- Question: does the scoped re-draft prompt have its own `PROMPT_VERSION`?
- Options: a second version constant / one shared `PROMPT_VERSION`.
- Decision: one shared `PROMPT_VERSION` (now 9: the scoped re-draft ask is new); it is bumped on any change to `TASK` or to the scoped `ASK`, and a test pins the hashes of both against the version, so an edit without a bump fails.
- decided by: orchestrator (design call)
- status: pending owner confirmation
- Reasoning: the usage log records one version per call whichever prompt made it; two constants could drift, a pinned hash cannot.

## 2026-10-11 | Admin accepted formulas | Web budgets and page placement
- Question: where do the accepted formulas go on the web, and do the perf budgets move?
- Options: a section on the Feature requests page in its own lazy chunk / a new Admin section and route / inline in the page chunk.
- Decision: a lazy section on the existing Feature requests page (no new workspace section, no new Start page). Budgets: the page chunk +370 B (the dynamic import and its Suspense fallback), the Screeners page chunk +304 B (the new operation joins the shared generated document map it carries), and a first budget of 3900 B for the section's own chunk. Reasons are in `apps/web/perf-budgets.json`.
- decided by: owner (confirmed 2026-10-11)
- status: final
- Reasoning: the owner confirmed the placement and approved the budget raises; the Screeners page also makes one more request (49 -> 50) because the section shares `ExpandableTable` as its own chunk. The brief allows a raise with a written reason; an inline section would have cost the page 3.9 kB.

## 2026-10-11 | Admin accepted formulas | Erase and curated events
- Question: does erasing a user also null the accepted-formula text on events curated into the golden set, and does an erased user still count in the admin `users` number?
- Options: confirm the criteria rule (curated events keep their payload; erased users still counted) / erase curated formula payloads too.
- Decision: confirm: the same rule as the criteria payloads.
- decided by: owner
- status: final
- Reasoning: one rule for everything in a drafting-event payload.

## 2026-10-12 | Describe it wrap-up | Enum values not built, one contradiction accepted
- Question: are enum values for index-only fields shown to the model; is "volatile squeeze" (ATR >= 3% and a Bollinger squeeze) served without the model?
- Options: build enum values now / measure first; fall through to the model / serve it.
- Decision: enum values are not built (the live Haiku run of 2026-10-12 shows no wrong-enum drops: 0 drops of any kind); "volatile squeeze" is served (a squeeze is measured against the name's own history, ATR% is an absolute level, so the pair is a real screen, not a contradiction).
- decided by: orchestrator (design call)
- status: pending owner confirmation
- Reasoning: enum values would cost prompt budget the measurement does not justify; the Opus architect reviewer of #560 agreed on the second.

## 2026-10-12 | Describe it phrasebook shortcut | Stamp on a no-model draft
- Question: what does a draft made by the phrasebook (no model call) record as its prompt version in the feedback event?
- Options: the shared prompt version, stage only in the payload / `phrasebook:<hash of the structured entries>` / null.
- Decision: `phrasebook:<short hash of the structured entries>`.
- decided by: Fable on the owner's behalf
- status: pending owner confirmation
- Reasoning: no prompt made the draft, so the prompt version would be a false attribution; the payload (where the stage lives) can be nulled while the column survives; the hash is site config, not personal data.

## 2026-10-12 | PR #566 (Describe it retype) | Stale answer after the screen changed
- Question: a retype's answer arrives after the trader changed the screen: apply it, or drop it, and does the call still count against the daily limit?
- Options: apply the merged draft over the later edits / drop it and keep counting the call / block every edit during the wait.
- Decision: drop it, keep the call counted; the card says "Your screen changed while this redrafted", with its Guide help and Try again.
- decided by: Fable on the owner's behalf
- status: pending owner confirmation
- Reasoning: applying it would undo the trader's later edits; the model call did return a draft, and the cap counts answered calls.

## 2026-10-12 | PR #566 (Describe it retype) | Lifting the daily limit in the browser
- Question: after a retype hits the daily limit, when do the cards' Retype buttons work again?
- Options: until the page reloads / when the server's `retry_after_s` elapses.
- Decision: when `retry_after_s` of the 429 elapses (one timer for every card); with no `retry_after_s`, until reload.
- decided by: Fable on the owner's behalf
- status: pending owner confirmation
- Reasoning: the limit clears when the exchange day turns, which the server states; reload-only would keep the buttons off for a user who stays on the page.

## 2026-10-12 | PR #566 (Describe it retype) | The Guide states the retention of retyped words
- Question: does the Guide say how long retyped words are kept?
- Options: refer to the sentence's rule / state the 12 months.
- Decision: state it: "kept for 12 months, like the sentence you first typed, then removed", in the retype entry and the "Write the sentence" section of the Describe it Start page, so both agree.
- decided by: Fable on the owner's behalf
- status: pending owner confirmation
- Reasoning: the 12-month rule is the owner's (2026-10-11, "Raw sentence retention"); a user-facing text about stored personal text should carry the number.

## 2026-10-12 | PR #566 (Describe it retype) | An abandoned retype is not refunded
- Question: a retype the trader started and left (left the page, or the answer arrived stale) used a model call: does it count against the daily cap?
- Options: refund it / count it.
- Decision: it counts, no refund; the Guide's `describe_part_stale` entry says so.
- decided by: orchestrator (design call)
- status: pending owner confirmation
- Reasoning: the cap counts answered calls (`part_redraft_limit`, ADR 0041 amended 2026-10-12); the server cannot tell an unused answer from a used one, and a refund path would add state for a rare case.

## 2026-10-16 | PR #577 (post-session workflow) | A failed post-session step alerts like a failed nightly step
- Question: should a failed edge-eval, descriptions or verify (now outside the nightly) alert?
- Options: report only / the same alert as a failed nightly step.
- Decision: the same alert, through the nightly's notifier; also when `[post] max_duration_minutes` is exceeded.
- decided by: owner
- status: final
- Reasoning: these steps used to appear in the nightly's alert; moving them out must not silence failures.

## 2026-10-17 | PR #589 (Describe it connector) | The connector token's labels and reading
- Question: what does the connector between part cards say, and how is it read aloud?
- Options: the logic's own names (AND, OR, AND NOT) / the trader's register.
- Decision: and -> "and", or -> "or", and_not -> "but not" (one negation beside a card that already states the exclusion, never two); read as "joined by {words}, read as {label}" (just "joined by {words}" when the words equal the label); the Guide entry `describe_part_join` explains it.
- decided by: Fable on the owner's behalf
- status: final
- confirmed: owner 2026-10-18
- Reasoning: the traders' own words (but, except, unless) stay visible and the reading beside them is what they would say; a second negation would read as a double negative.

## 2026-10-17 | PR #589 (Describe it connector) | When the connector token shows
- Question: which joins get a token between part cards?
- Options: every join / only those that change the reading.
- Decision: join "or" and "and_not" always; join "and" only when the words are not a plain conjunction: hidden when every word (commas ignored) is a plain conjunction: and, with, plus, also, then, or there are no words; shown for but, yet, while, although, though, whereas, as long as, so long as, only if, provided (that).
- decided by: orchestrator (design call)
- status: final
- confirmed: owner 2026-10-18
- Reasoning: a token between every pair of cards is noise; "but" or "only if" changes how the second part reads and is where a misread hides.

## 2026-10-17 | PR #590 (ADR 0071) | Boolean groups: a tree in the engine, one level in the Builder
- Question: one level of groups, or a full boolean tree?
- Options: keep formulas / one level `any` / `none` / inline tree / tree by reference in the engine with a one-level Builder.
- Decision: a tree by reference (`all` / `any` / `none`, depth <= 4) in the spec and engine; the Builder edits one level for now.
- decided by: owner
- status: final
- Reasoning: the engine should express any condition the trader means; the UI stays simple on phones until a tree editor is wanted.

## 2026-10-17 | PR #590 (ADR 0071) | Describe-it precedence case by case
- Question: one global precedence rule for mixed and / or / except in a sentence?
- Options: OR binds tighter than AND globally / decided per phrasing.
- Decision: per phrasing, each a golden case with its expected tree that the owner verifies in the Describe-it PR.
- decided by: owner
- status: final
- Reasoning: natural language is ambiguous; the owner wants to see and check each reading.

## 2026-10-17 | PR #590 (ADR 0071) | Soft and score criteria inside groups
- Question: may a `soft` or `score` criterion sit inside a group?
- Options: hard only in v1 / every mode everywhere.
- Decision: every criterion keeps `hard` / `soft` / `score`; `all` sums penalties, `any` takes its best member, `none` negates operators and keeps tolerances.
- decided by: owner
- status: final
- Reasoning: soft and score are how traders express preference; groups must not take them away.

## 2026-10-17 | PR #590 (ADR 0071) | Existing boolean formulas are not converted
- Question: offer to convert saved boolean formula features into groups?
- Options: convert / leave.
- Decision: leave them; new drafts use groups.
- decided by: owner
- status: final
- Reasoning: they keep working; conversion adds risk for no gain.

## 2026-10-17 | Edge build plan (EB) | Verdict bar (t-statistic)
- Question: Verdict bar (t-statistic)?
- Options: t >= 2 for Promising (keep) / t >= 3 for Promising.
- Decision: Promising stays at t >= 2; Works needs t >= 3 on both series.
- decided by: owner
- status: final
- Reasoning: Harvey-Liu-Zhu's t > 3 applies to claiming a new factor (Works); Promising remains a research state.

## 2026-10-17 | Edge build plan (EB) | Short and long-short results as a verdict basis
- Question: Short and long-short results as a verdict basis?
- Options: long only / short ok and long-short diagnostic / both.
- Decision: a short result on liquid names may be the basis; long-short is diagnostic only.
- decided by: owner
- status: final
- Reasoning: an avoid list is actionable with a read-only broker; a long-short spread needs shorting the owner does not do.

## 2026-10-17 | Edge build plan (EB) | Historical option chains
- Question: Historical option chains?
- Options: buy now / not now.
- Decision: not now: H8 model P&L ships, H13 chain P&L accrues from 2026-10-02.
- decided by: owner
- status: final
- Reasoning: no new spend.

## 2026-10-17 | Edge build plan (EB) | Tiingo Power
- Question: Tiingo Power?
- Options: extend a month / pull within the bought month.
- Decision: pull the 2010+ history and the outcomes backfill by 2026-11-09.
- decided by: owner
- status: final
- Reasoning: no new spend.

## 2026-10-17 | PR #599 (Explore features tab) | History copy covers every instrument rollup
- Question: may the history copy (ADR 0060) grow to every instrument rollup, about +1.34 GB on the Mac (90% full, 20 GiB free), to cut the Features tab's history reads?
- Options: accept the disk / keep the copy to market tables and bars only.
- Decision: accept; release #599.
- decided by: owner
- status: final
- Reasoning: the Features tab's history reads drop from 6.7-8.0 s to 1.3-1.9 s per ticker; the copy stays within its 2.6 GB budget.

## 2026-10-17 | PR #619 (debt rules d to g) | Finance leases stay in total_debt
- Question: may `balance_sheet@v1.total_debt` include finance lease obligations where the SEC tag does (rules d to f, and the current part of c and e through `DebtCurrent`)?
- Options: keep them, labelled per rule in the field guide (as most data sites do) / exclude them and leave those filers NOT_TAGGED.
- Decision: keep them; operating leases are never in debt.
- decided by: owner
- status: final
- Reasoning: the tag does not split finance from operating leases in the filer's figure; excluding it would leave about 70 of 259 untagged companies null.

## 2026-10-17 | PR #643 (FINRA short interest / short volume) | Learned fits blocked, harness scoring allowed
- Question: FINRA's website terms (restriction (m)) bar use with machine learning / predictive analytics; the API terms we pull under do not. Does the ban stop only learned models, or also the edge harness scoring rule screeners built on these tables?
- Options: (a) block learned fits only (edge-scorer training frame, winners-study discovery probit in `services/evaluation/discovery` / `quant.probit`), harness may score screeners using them / (b) also stop the harness from scoring such screeners.
- Decision: (a), applied to every FINRA-derived feature whatever its source (API or cdn backfill files), as one licence tag on the feature groups with a fitness test that no training frame or probit input reads a tagged feature; the FINRA rows never reach the TextModel seam. The edge harness may score rule screeners that use them.
- decided by: Fable on the owner's behalf
- status: final
- confirmed: owner 2026-10-18
- Reasoning: the clause targets a program that learns or predicts from the data, and it sits only in the website terms (the cdn files), not the API terms. The harness evaluates a fixed, human-written rule after the fact (hit rate vs base rate, lift, deciles); nothing is fitted and no estimate becomes a model, so it is an audit, not predictive analytics. Use is personal and non-commercial with no redistribution, so the residual risk is remote, while knowing whether a short-interest screen has an edge is the reason to ingest it. Reversible: (b) is one PR (extend the tag check to the harness) if the owner disagrees. Matches the owner's plan "rule screens only, never a learned scorer".

## 2026-10-17 | PR #646 (EB H3 outcome sides) | A long-short edge's verdict state
- Question: what does an edge whose outcome is a long-short spread show as its verdict, given a spread is never a basis?
- Options: Waiting on data with a reason / its own state, Diagnostic only.
- Decision: its own state, `diagnostic_only`, with a Guide entry; the figures stay on the page.
- decided by: orchestrator (design call)
- status: pending owner confirmation
- Reasoning: Waiting on data says a result is coming; a spread's never becomes a verdict, so the word would mislead.

## 2026-10-17 | PR #646 (EB H3 outcome sides) | Assumed borrow cost of a short leg
- Question: what borrow cost does a short leg pay, and are hard-to-borrow names excluded?
- Options: flat 100 bp a year, no exclusion / flat rate plus a hard-to-borrow exclusion / no borrow cost.
- Decision: 100 bp a year (`verdict.toml [edge_costs] borrow_bps_annual`, per outcome overridable), no hard-to-borrow exclusion; the $5M ADV floor stands in. The limitation is recorded in ADR 0053.
- decided by: orchestrator (design call)
- status: pending owner confirmation
- Reasoning: no borrow data is stored, so any exclusion would be a guess; a flat assumption is stated and visible.
## 2026-10-17 | EB H2 (SEC acceptance time) | Scope of the acceptance-time fix
- Question: which groups read facts by SEC acceptance session, and where does the session rule live?
- Options: only `financials` and `fundamentals` / every group that reads the SEC facts; the rule only in `data.shares` / also in `core/time/calendar.py`.
- Decision: (3) `growth_history`, `income_statement`, `cash_flow` and `balance_sheet` also move to v2 reading the `_accepted` inputs, one backfill, rollup and retire window; (4) the `instruments/statements_accepted` input stays; (5) `calendar.acceptance_session` (strictly before the close counts that session) is the one scalar rule, for H4's 8-K fix. The 8-K `events/filing` `known_from` has the same bug (the New York acceptance day, not the session whose close it follows); it is fixed in H4, not in this PR.
- decided by: orchestrator (design call)
- status: pending owner confirmation
- Reasoning: a partial fix would leave the same one-session look-ahead in four groups that share the input and its backfill.

## 2026-10-18 | EB H6 (decoy battery) | What the decoy battery is, and what it changes
- Question: how are the standard decoys named, ranked and compared, and what do the stratified draws change?
- Options: `@standard` expanded at load into `Edge.baselines` / expanded inside the harness; the stratified draws as a second set in the same leg row / a second leg row; overlap and spread gap in the job report / a new `edge_eval` column.
- Decision: expand at load (the run hash then follows the list, no existing edge's hash moves); store the stratified sums in new `strat_*` columns of the same leg row (leg v3, `LEG_VERSION` 3) and as `random_sector:<screener>` rows of role `random`, so every reader of the uniform draws is untouched; report the Jaccard overlap and the spread gap in the `edge-eval` job result and text report only; `beta_low` ranks by `factor_betas.beta_mkt` (five-factor), `ivol_high` by the residual volatility, MAX over 21 sessions, Amihud over 63; the existing edges keep their baseline lists.
- decided by: orchestrator (design call)
- status: pending owner confirmation
- Reasoning: the smallest change that keeps hashes stable, adds no table, and leaves what users see (the verdict reads the uniform draws) as it is until the owner decides whether the stratified percentile joins it.

## 2026-10-18 | EB H4 (event-class framework) | Subtypes, the filing group, and what is left out
- Question: how are subtypes read, which classes ship on stored data, and does the folder cap force a new feature-group folder?
- Options: one subtype label field per class (the plan) / per-subtype count and date fields; keep every group in `rollups/corporate` / a folder `rollups/events` for the event-class groups; add `ex_dividend`, `macro_release` and `lockup_expiry` / leave them until their fields exist.
- Decision: a subtype is its own count and date fields (an 8-K item: the latest filing only would miss an item filed before another 8-K) or a label field that must read a value (index changes, date-shift direction), one mechanism in `EventField.subtypes`; `filing_events@v1` holds the 8-K items 1.02, 2.05, 3.01, 4.01, 4.02, 5.02, NT and tender offers (SC TO-T joins the kept forms); `earnings_date_shift@v1` with a 7-day threshold; `rollups/corporate` is at its 10-module cap, so the event-class groups (and `index_changes`, moved) live in a new `rollups/events` folder; `ex_dividend`, `macro_release`, `lockup_expiry` are left out (ADR 0053 amendment, point 4); filings are read by the acceptance session recomputed from `ts`, never the stored `known_from`.
- decided by: orchestrator (design call)
- status: pending owner confirmation
- Architect review (PR 655): keep the six 8-K items (1.03 and 2.06 later), keep the 7-day threshold, approve the `features/rollups/events` folder.
- Reasoning: the item list and the 7-day threshold are judgement calls the owner may widen; a stale `known_from` left in the store must not leak, so the reader does not trust it; a new folder is the layout rule's answer to a full one.

## 2026-10-18 | PR #642 (ADR 0071 PR 6) | Describe-it precedence of connectors
- Question: how do "or", "and" and "except" combine in a drafted sentence?
- Options: and binds tighter than or, a comma or "ideally" starts a new condition, an exclusion is its own gate / a flat left-to-right reading / the model decides per sentence.
- Decision: and binds tighter than or (as the expression parser does); a comma or "ideally" starts a new condition, so an "or" never reaches across it; "except A or B" is neither; "except A and B" is neither only for a bare "and" (", and" ends the exclusion); "A or B except C" is (A or B) and not C. One golden case per phrasing pins it.
- decided by: Fable on the owner's behalf
- status: final
- confirmed: owner 2026-10-18
- Reasoning: one rule set gives the same reading every time and a wrong reading is one line and one golden case; the owner verifies the cases in the PR. Proposed by the Opus architect in the review; Fable, briefed with the options, confirmed it unchanged: "and" narrows a condition and "or" offers alternatives, the narrower screen costs a few missed names where a wider one buries the idea, and the Builder's plain-English line shows any wrong reading before a save. No golden case changes.

## 2026-10-18 | PR #642 (ADR 0071 PR 6) | Flat fallback when a part cannot sit in a group
- Question: what does a draft do when an "or" or exclusion has a part that is a formula, a missing request, a dropped criterion or words nothing maps?
- Options: keep the draft flat as before groups / group the available sides only.
- Decision: keep it flat; only the formula case gets the verifier's doubt (draft one boolean formula), every other block leaves a visible note ("... is not available, so the 'or' or exclusion is not applied"); two kinds of instrument joined by "or" are doubted (one security_type criterion).
- decided by: Fable on the owner's behalf
- status: final
- confirmed: owner 2026-10-18
- Reasoning: grouping the available sides would silently change the meaning (an "or" side dropped makes the other side mandatory). Proposed by the Opus architect in the review; Fable, briefed with the options, confirmed it and asked that the note say the other conditions apply on their own (done): blocking the draft would throw away the parts that worked.

## 2026-10-17 | PR #644 (E1c option-implied features) | IBKR IV30 change as a personal-licence feature
- Question: does the IV-change edge (c03) get a long-history IBKR variant beside the chain-derived one?
- Options: chain-derived only (history from 2026-10-02) / also `ibkr_iv_chg_5d` and `ibkr_iv_chg_21d` from IBKR's IV30 history (about 502 sessions).
- Decision: add `ibkr_iv_history@v1` with both, `licence = "personal"`, optional like `ibkr_iv@v1`; `cp_iv_history@v1` stays open. Its guide entries say IBKR's IV30 blends calls and puts, so it tests the overall IV-change effect, not the call-minus-put split.
- decided by: orchestrator (design call)
- status: pending owner confirmation
- Reasoning: settled by the architect reviewer of #644 (the format accepts no `architect` decider); the edge can be scored now instead of from November; the read-only broker boundary is untouched (it reads a stored rollup).

## 2026-10-18 | EB H6 (decoy battery, architect review) | Factor betas without a sector, and unmeasured decoys
- Question: how do ivol and beta exist over history when the sector map starts 2026-10-02, and how is a decoy with no figure counted?
- Options: five-factor fit for all (empty history) / four-factor fit for every name with `beta_sector` only where a sector exists; leave a figure-less decoy out / count it as not measured.
- Decision: four-factor fit (market, size, momentum, value) for `ivol_252d` and four betas, `beta_sector` from a five-factor fit where a sector exists (else NO_SECTOR), `relative_strength@v1` required; a decoy with no lift or spread is "not measured" ("n of m measured") in the verdict and flagged in the decoy report; the stratified draws read the later sector snapshot before 2026-10-02, as the screeners do (accepted).
- decided by: orchestrator (design call)
- status: pending owner confirmation
- Reasoning: the history the decoys are measured over has no sector; a gate on it would empty two decoys, and a silent omission would let "beats every baseline" pass untested.

## 2026-10-17 | EB H8 (option model P&L) | Short delta-hedged side, stored basis, short put
- Question: how is the short side of the delta-hedged straddle expressed, where does `basis = "model"` live, and when does the short-put P&L land?
- Options: a `side` key / a separate structure value; a stored `edge_eval` basis column now / with the chain P&L grain (H13); short put in H8 / a follow-up PR.
- Decision: a separate structure value `delta_hedged_atm_short` (Guide entry, coverage, fitness test; no `side` key); the stored basis column waits for H13 (today `Outcome.basis`, page text and Guide); the short-put P&L is a follow-up PR.
- decided by: orchestrator (design call)
- status: pending owner confirmation
- Reasoning: a value per structure keeps every position one enum value with its own Guide entry; a column on a stored table is a schema change that belongs with the chain grain; a put needs a strike key and a put price that H8's three straddle structures do not.
## 2026-10-18 | PR #645 (E1b filing_activity) | The 8-K span ends at the previous session
- Question: may `filing_activity@v1.filing_count_5d` count 8-Ks through the session itself?
- Options: through S, with coverage read from row presence / through S-1 (filings known before S-1's close), coverage from the filings walk's `walked_to`.
- Decision: the span ends at S-1 (filings that became known on or before S-1, so accepted before S-1's close, over the 5 sessions ending there; only 8-K and 8-K/A rows), and the value is null unless a clean walk of a session on or before S reached S-1. `feature.news_free_5d` means no 8-K through S-1 and no earnings window in the last 5 sessions.
- decided by: orchestrator (design call)
- status: pending owner confirmation
- Reasoning: the nightly starts about 18:00 New York time and SEC lists 17:30-22:00 acceptances in the next day's index, so S's own 8-Ks are usually unstored when the nightly runs; counting through S read 0 live and 1 on a recompute. The span through S-1 gives the same value live and in a backtest. A history before the first nightly walk reads null. Known limits: the session after a market day EDGAR was closed reads null, and on a SEC-only holiday Friday an after-17:30 acceptance can be missing from the walked index until the next walk.

## 2026-10-18 | filing_activity follow-up to PR #645 | History before the first nightly walk
- Question: how does `filing_count_5d` get values for sessions before the first nightly walk, so `volume_shock_no_news` can be backtested?
- Options: leave null until walks accumulate / let a full per-CIK read (`covers_since` on or before the span, run of S-1 or later) cover past sessions for that CIK only / treat the backfill as covering every CIK.
- Decision: `data/events.filing_coverage(reader)` is the one reader of the filings task's coverage (`walks`, `reads`, `asked_since`, `walked_to`; the ingestion's own copies are gone); `filing_activity@v1` reads its per-CIK reads through the `filings/read` input, whatever the session, and counts a CIK's 8-Ks when a clean walk covers S-1 (as before) or a read of that CIK covers the span. No version change: values only appear where they were null. Rebuild: `algotrade-ingest rollups --from <first session> --to <last session> --only filing_activity@v1` (owner's go-ahead for the live store). No SEC-closed-day list: the session after Columbus Day or Veterans Day stays null until a walk reads past it (fail closed, as accepted).
- decided by: orchestrator (design call)
- status: pending owner confirmation
- Reasoning: the 8-Ks known on a past session do not change once read, so a later full read of a CIK says its history is complete; coverage stays per CIK because a read says nothing about another company, and an instrument with no 8-K in the lookback stays null (no CIK to match). Past sessions use the knowledge of a later run for coverage only, never for a value (rows are still bounded by `known_from <= S-1`).

## 2026-10-18 | EB H7 (buy/hold bands) | Where a band applies, long_short, and what the net series is
- Question: which edges may carry `hold_rank`, what happens for `long_short`, how is a name's cost split between entry and exit, and which figures follow the banded series?
- Options: allow a band on every schedule / only where decision sessions do not overlap; a band on both legs of a spread / refuse it; the whole round trip at entry / half in, half out; replace `pick_values` (and so every statistic) / keep gross figures and bind only the net series.
- Decision: `long` and `short` `excess_return` with an integer `top_k`, on `month_end` or `every_session` at horizon 1; `long_short`, event and calendar schedules refused in the document; an entry and an exit each pay half a round trip, the last session exits (charged) and a coverage gap closes every position; hit rate, lift, decile spread, effect size and the floor stay the legs' own, the net series (Sharpe, deflated Sharpe, PBO, `mean_excess_picks`), the cost rows and the break-even follow the band; the break-even's turnover is read from the slope of the stored cost rows, no new column; hit counts at cost levels and the trade ledger stay per round-trip trade (follow-up).
- decided by: orchestrator (design call)
- status: pending owner confirmation
- Reasoning: the schedule limit is stricter than needed (plain-schedule windows never overlap; loosening is a later PR); a spread has no cost rows and no single book; half and half makes a name held through pay exactly one trip over its stay; gross figures must not move so the verdict's evidence is the same picks, and only what a trader pays changes.

## 2026-10-18 | EB H7 (buy/hold bands) | One full re-run after LEG_VERSION 4
- Question: who pays the re-run that LEG_VERSION 3 (H6) and 4 (H7) each force?
- Options: a re-run after each / one after both.
- Decision: one full re-run after both merge (`algotrade-backtest evaluate-edges --full`; the PR gives the command); H7 does not run it against the real store.
- decided by: orchestrator (design call)
- status: pending owner confirmation
- Reasoning: every stored leg is recomputed by either bump, so two runs would spend the same hours twice.

## 2026-10-18 | PR #651 (D6, Form 4 insider transactions) | Storing the reporting owner's CIK and officer title
- Question: may the insider transaction table store `owner_cik` and `officer_title` (public EDGAR fields that identify a natural person), or only a hashed owner key plus role flags?
- Options: store `owner_cik` + `officer_title` as filed / store a salted hash of the owner CIK + role flags only / store role flags only (no per-person key).
- Decision: store `owner_cik` and `officer_title` as filed, no names, no other identifiers (no address, no owner name from the XML). The table carries the Form 4 public filing data only; the UI shows counts and roles (distinct insiders, officer / director / 10%-owner), never a per-person list. Retention: as the other event grains (indefinite, point-in-time), per D6's plan. `docs/architecture.md` section 10 ("PII: none stored") gets a one-line amendment in a follow-up: "public SEC filer identifiers (reporting-owner CIK, officer title) are stored as filed; no names."
- decided by: Fable on the owner's behalf
- status: overruled
- confirmed: owner 2026-10-18
- Reasoning: the owner CIK is an SEC public identifier the data set is keyed on; a hash buys nothing (the hash of a public id is trivially reversible against EDGAR) and loses the join to later filings, amendments (4/A) and the deep-dive dossier. Officer title is attribute data a cluster-buy edge weighs (CEO / CFO buys vs. director buys), stored as filed with no name. The cluster-insider-buy edge needs a distinct-insider count, so a stable per-person key is functionally required. Data never enters the public repo (store is local, git-ignored); the read model serves aggregates. Precedent: ADR 0040 keeps emails (private personal data) out of the repo, not public filing data out of the store. Erasure and shorter retention are owner-only decisions (log 2026-10-11), so the default event retention stands until the owner says otherwise.

## 2026-10-18 | EB H11 (residual returns) | Betas read before S, sector term, no nightly step yet
- Question: which session's betas measure a window's residual, what to do with the sector loading, and does the task join the nightly workflow in this PR?
- Options: betas at D / at the session before S / at S; the four-factor residual only / add the sector term where `beta_sector` is set (two fits' betas) / a single five-factor fit; a nightly step now / the task and its backfill command first.
- Decision: the betas of `previous_session(S)` (exact partition, never an older one), the sector SPDR term only where `beta_sector` is set (the brief's rule, with the two-fit mix stated in the ADR), the task registered with its backfill command and no workflow step in this PR; the leg-reuse stamps do not cover the residual partitions (ADR 0053 amendment, limit a).
- decided by: orchestrator (design call)
- status: pending owner confirmation
- Reasoning: the session before S is D for the usual offset of 1 and never holds a window return for a larger one; the sector term is what the plan lists, and the mixed-fit inconsistency is small and visible; a nightly step needs the workflow-step tests and a real-store cost measurement the PR cannot run.

## 2026-10-18 | EB H11 (residual returns) review | Four-factor betas only, stamps, nightly step, settlement
- Question: how to resolve the architect's four findings on the residual-returns grain (sector counted twice, stale legs, no nightly step, settlement raising for a residual edge)?
- Options: sector from `beta_sector` / drop it until a five-beta `factor_betas@v2`; leave the stamps / add the residual partitions to them; follow-up step / the step now; attach residuals in settlement / catch the error per edge.
- Decision: residual on the four-factor betas only (market, size, momentum, value; a `factor_betas@v2` with all five betas of one fit is needed for sector; this supersedes the 2026-10-18 entry's sector choice); the stamps cover the residual partitions when a plan measures them (combined sequence and `knowledge_ts`); the optional nightly step `residual-returns` with an acceptance check; settlement attaches the residual rows, an unstored one waits and is skipped with a reason after the grace window.
- decided by: orchestrator (design call)
- status: pending owner confirmation
- Reasoning: the stored sector slope is from a different fit than the other four, so adding it counts sector exposure twice; a leg stored before the backfill must not stand for ever; an unscheduled grain goes stale; one residual edge must not stop every followed edge's settlement.

## 2026-10-18 | EB H5b (time-series base) | How a window edge is declared and judged
- Question: how does a raw-return, named-instrument edge fit the edge document and the verdict without a new outcome kind or stored column?
- Options: a new outcome kind `raw_return` and a new `edge_eval` column for the timing Sharpe / keep `excess_return` over benchmark `none` (legal only with `base = "out_of_window"`), named instruments as one `instrument.symbol in [...]` rule, the Welch t in the verdict's existing t slot and the timing Sharpe in the run record.
- Decision: the second: no new outcome kind, no schema change; `decile_t` carries the Welch t (Promising t >= 2, Works t >= 3), `hit_rate` / `base_rate` the positive-window shares, `sharpe` / `picks_t` / the deflated Sharpe the in-window series, the random window sets are `role = random` rows; no variants and no per-session series, legs or ledger for such an edge.
- decided by: orchestrator (design call)
- status: pending owner confirmation
- Reasoning: the verdict, trial log and frozen split are reused unchanged, so a window edge cannot be judged more leniently than a cross-section one; a stored column and a series for a screen-less edge are a schema decision for when a page shows them. Known gap: the timing-versus-buy-and-hold Sharpe is in the run record only.

## 2026-10-18 | EB H5b (time-series base) | The outcomes seam is a forbidden contract, not a widened one
- Question: the plan says to widen "only cross_section/harness.py reads outcomes" to name `time_series/harness.py`.
- Options: widen the named-modules list only / also add an import-linter contract confining the new package.
- Decision: both: `time_series/harness.py` joins the named modules of `test_edge_outcomes_expressible.py`, and a forbidden contract keeps every other module of `services.evaluation.time_series` off `algotrade.data.outcomes`; the protected-module contract of 0053 (only `services.evaluation`) is unchanged.
- decided by: orchestrator (design call)
- status: pending owner confirmation
- Reasoning: the package-level contract already admits all of `services.evaluation`, so widening it would change nothing; the per-package contract is what makes "one reader" true for the new folder.

## 2026-10-18 | EB H5b (PR 660 review) | The paired series carries the Sharpe, t and deflated Sharpe
- Question: the in-window Sharpe, picks t and deflated Sharpe on raw window returns read drift, not timing.
- Options: raw in-window series / each window minus the first stretch tiled right after it (unpaired windows counted, never filled).
- Decision: the paired series; `decile_t` stays the Welch t, worded "In-window minus out-of-window t (Welch)" through `EdgeFacts.base`; several instruments deflate with the variance of their Sharpe ratios; `year_part` / `regime_part` slices added; Guide term `base_out_of_window`.
- decided by: orchestrator (design call)
- status: pending owner confirmation
- Reasoning: a rising instrument would otherwise pass Works on drift alone; the paired difference removes the instrument's drift without a model.

## 2026-10-18 | EB E3 (event edges and avoid lists) | Short-side edges, a delayed tender entry, and what is filed blocked
- Question: how are the avoid-list edges tested, how is a tender offer's "after expiry" entry expressed, and what happens to ideas whose event class or data is missing?
- Options: avoid lists as a long edge read for a negative lift / as `side = "short"` (O2); tender entry at the filing / 21 sessions after it / wait for an expiry field; missing classes skipped / filed `blocked` with the reason / classes added in this PR.
- Decision: 8-K Item 4.02 and NT late filers are `side = "short"` edges over event names, ranked by dollar volume (the harness's short leg takes the lowest scores, so the screeners order ascending and the most liquid filer is shorted first); the tender edge enters 21 sessions after the filing (a tender offer stays open at least 20 business days; the expiry date is not stored, extensions enter early, and SC TO-T joins SC TO-I in one column); spinoff_drift, reverse_split_distress_filter and thematic_etf_launch_fade are filed `blocked` with what is missing (the classes spinoff, reverse_split and etf_launch in `EVENT_CLASSES` and `EVENT_FIELDS`, which this PR does not touch); `eight_k_item_flag` flags 4.02, 4.01 and 5.02 within 20 sessions for the avoid screen while the edge tests 4.02 only; `earnings_gap_volume@v1` adds the last report's volume ratio (the four-report mean in `earnings_reaction@v1` is a habit of the name, not the event).
- decided by: orchestrator (design call)
- status: pending owner confirmation
- Reasoning: a long edge reads an avoid list's confirmation as a negative lift (Not working), the short side states the same claim so that it passes; a dense-score short leg over a universe fills up with unflagged names when few are flagged, so a non-event schedule cannot test a small flagged set; entering at the filing would trade the offer's own period, not the post-expiry dip the thesis is about; a blocked document keeps the thesis, the bar and the missing pieces on file without a placeholder passing as a test.

## 2026-10-18 | EB E4 (option P&L, closed-end fund and ETF flow edges) | What is a candidate, what is blocked, and the fund features
- Question: which of the E4 and E6 ideas can be measured by the merged harness today, and how do the fund features read data the universe does not cover?
- Options: every idea a candidate / a candidate only where the outcome can be priced and the inputs have history, the rest `blocked` with the reason; fund features as a new `applies_to` value / `any` with rows only for funds.
- Decision: c12, c14, c18 (IBKR IV30, 502 sessions, horizons inside the 10 to 42 sessions the parser prices) and etf_flow_pressure (iShares counts from 2026-10-17, accruing) are candidates; c13 (no long-tenor volatility history), c16 and c17 (a 3-session and a 1-to-2-session position cannot be priced by a 30-day volatility; a short-tenor field is needed), closed_end_fund_discounts and cef_distribution_trap (closed-end funds are not in the covered universe, so no bars; the payout data is not stored either) are `blocked`; c19 (index chains not stored) and etf_premium_discount_reversion (no ETF NAV history) are not filed. `cef_nav@v1` and `etf_flows@v1` carry `applies_to = any` and rows only for funds with a NAV or a count (a new `applies_to` value is a framework change); `cef_nav@v1` is `licence = "personal"` (Tiingo). c14 reuses `ivol_high` on the liquid optionable universe. No figure is filed as `[published]`: the sources' numbers are decile or quintile spreads or one-leg premium averages.
- decided by: orchestrator (design call)
- status: pending owner confirmation
- Reasoning: a candidate whose outcome the parser refuses, or whose inputs have no history, would show a verdict-less row for months; a blocked document keeps the thesis, the bar and the unblock path on file. Adding closed-end funds to the universe is an owner decision (coverage, nightly bars and the Tiingo symbol budget; ADR 0013), listed in the hand-back, not decided here.
## 2026-10-18 | EB H10 (portfolio outcomes) | What a book is judged on and how it is built
- Question: how is an allocation edge (a weighted book against a blended benchmark) measured, and what do Promising and Works rest on when there is no base rate over names?
- Options: a new outcome kind in the harness / a path in the backtest engine; a mix read from the grain / computed from the constituents' rows; slots a `top_k` leaves unfilled go to cash / are left out; win rate and lift against the benchmark's hit rate / no base rate; Works on the decile t as for a ranking / on the picks-series t.
- Decision: a `portfolio_return` kind in the harness (ADR 0074); the mix computed from the constituents' own `fwd_return` at the same S through the resolver (a missing constituent leaves the session out with its reason); unfilled slots are NOT put to cash (only a `CASH` pick or an empty pick set is); no base rate, lift or random draws for a book; Promising needs the picks-series t of 2 and Works of 3, with the decile t beside it only when about 20 names are ranked; decoys compared on the mean excess return of their own books.
- decided by: orchestrator (design call)
- status: pending owner confirmation
- Reasoning: the harness already owns the frozen split, the trial log and the verdict, and the engine none; a base rate over ten ETFs is a coin flip and a decile of ten names is one name; putting unfilled slots to cash is a policy (a defensive default that changes what the screen means), so it waits for the owner; failing closed on a missing input keeps a book from being quietly re-weighted.

## 2026-10-18 | EB H10 (portfolio outcomes) | Leg v5 without a LEG_VERSION bump
- Question: does adding the book's weights to a leg need another full re-run of every stored leg?
- Options: bump `LEG_VERSION` to 5 / add nullable columns and leave the version.
- Decision: nullable columns (`weight_ids`, `weight_values`, `portfolio_reason`), no bump; the default weighting stays out of an outcome's identity.
- decided by: orchestrator (design call)
- status: pending owner confirmation
- Reasoning: no existing leg's content or key changes (a bump recomputes every leg for nothing); a portfolio edge's legs are new keys anyway. H6 and H7's bumps already force the one full re-run.

## 2026-10-18 | EB H10 (portfolio outcomes) | Unfilled slots are cash; Works for a book without deciles
- Question: when fewer names qualify than `top_k`, is the book re-normalised over them or is the rest cash? What does Works rest on for a book with no deciles?
- Options: re-normalise / unfilled slots in cash; picks-series t alone / both t series always.
- Decision: each unfilled slot is `1 / top_k` in cash (re-normalising puts the whole book in one name); a day before the first stored Treasury curve has no yield (no look-ahead); Works for a book rests on the picks-series t of 3 when there are no deciles, with deciles both t series.
- decided by: orchestrator (design call)
- status: pending owner confirmation
- Reasoning: architect review of PR 666; the cash rule is set before any edge stores legs, so no leg is invalidated.

## 2026-10-18 | EB H13 (chain P&L grain) | One UNMEASURED status per row, executable value, hedge with r = q = 0
- Question: when a hedge-day chain is missing or stale, is only the hedged P&L unmeasured or the whole row; is the harness value mid or executable; which rate and yield does our own hedge delta use?
- Options: hedged columns null, unhedged kept / the whole row UNMEASURED; mid-to-mid / ask in, bid out (half-spreads on the hedged value); the Treasury curve and dividend yield / r = q = 0.
- Decision: the whole row is UNMEASURED with the first reason (`STALE_CHAIN:<day>`, `NO_CHAIN:<day>`, `NO_DELTA:<day>`, `NO_EXIT_QUOTE`), every P&L null; the harness value is executable (a long pays the ask in and bid out, a short the reverse, the hedged value less the same half-spreads) while the mid P&L columns stay stored; the delta uses r = q = 0 and calendar days over 365.
- decided by: orchestrator (design call)
- status: pending owner confirmation
- Reasoning: one status then means one thing and the spec's "never a zero, never a silently filled stale chain" holds for every column; option spreads are the main cost of this trade, so a mid value would overstate it; a one-month delta moves under 1% with the curve and the yield, and r = q = 0 keeps the grain independent of the rates and dividend tables (ADR 0053 amendment 2026-10-18, item 5). The cost of the first choice is that a stale mid-window day also unmeasures an unhedged window.

## 2026-10-18 | EB H13 (chain P&L grain) | The basis is declared at filing; no stored basis column
- Question: with no pre-frozen chain history, how is the verdict's basis fixed, and does `results/edge_eval` get a stored `basis` column (H8 left it for H13)?
- Options: rank candidates on an in-sample slice that does not exist / the basis declared at filing, every row out of sample; a stored column / the basis from the document's kind, which is in the outcome hash.
- Decision: the basis is the declared screen and horizon (several undeclared candidates: Waiting on data); every chain row is out of sample; `Outcome.basis` is `"chain"` and no `edge_eval` column is added; how the Promising and Works rules read an empty in-sample t is left open for the architect review.
- decided by: orchestrator (design call)
- status: pending owner confirmation
- Reasoning: ranking needs the in-sample history the grain cannot have, and `choose_basis` already takes one declared candidate; a column on a stored results table is a schema change for a label the outcome hash already fixes, so a run cannot be mistaken for the other basis.

## 2026-10-18 | EB H13 (chain P&L grain) | Structures, tenor rule and where the grain is read
- Question: which structures and which tenor rule does the first chain grain offer, and does a mixed edge (price and chain variants) run?
- Options: only the straddles / also the short put by delta; the expiry nearest the tenor / the first at least the tenor out and not before the window's end; mixed edges allowed / refused.
- Decision: five structures (`atm_straddle_long|short`, `delta_hedged_atm[_short]`, `put_short` by delta), the grain stores the long position (`atm_straddle`, `put_delta_NN`); the first listed expiry at least `tenor_days` out and not before T; an edge and its `[[variants]]` are all `option_pnl` or none is.
- decided by: orchestrator (design call)
- status: pending owner confirmation
- Reasoning: one stored row serves the long, short and hedged edge; an expiry before T could not be held to the exit; the harness reads one outcome grain per run (reuse stamps and commit sequences are per grain), so mixing is refused at filing instead of silently reading the wrong table.

## 2026-10-18 | EB H13 (architect review of #664) | Hedge-day gaps cost only the hedged P&L; bid-0 quotes and delta limits
- Question: does a missing or stale chain on a session between entry and exit unmeasure the whole row, and how are far out-of-the-money and deep in-the-money legs read after a large move?
- Options: the whole row UNMEASURED (first entry) / only the hedged P&L, with a `hedge_reason`; a bid-0 quote and an unsolved vol are missing / a bid-0 quote reads as mid ask / 2 and an unsolved vol takes the delta limit (0, +-1).
- Decision: only the hedged P&L is lost (`hedge_reason` set, the row COMPLETE, a hedged structure's harness row excluded as unmeasured); bid-0 quotes and delta limits as above. This overrules the first H13 entry's "whole row UNMEASURED". r = q = 0 is accepted for v1.
- decided by: orchestrator (design call)
- status: pending owner confirmation
- Reasoning: the architect review showed the biggest moves would otherwise become NO_EXIT_QUOTE / NO_DELTA and flatter the short straddle, and a stale mid-window day would blank an unhedged window for no reason.

## 2026-10-18 | EB H13 (architect review of #664) | A chain edge can be Promising, never Works, until the verdict-basis rule says more
- Question: how do the verdict rules read an empty in-sample t for a chain basis declared at filing?
- Options: leave it open / the in-sample-lift criterion not applicable and a Works criterion that stays unmet.
- Decision: "out-of-sample lift keeps its size" is not applicable for a chain edge (Promising reachable); a Works criterion "basis fixed on an in-sample period" stays unmet (Works unreachable) until a later amendment of the verdict-basis rule; written into that amendment and the Guide.
- decided by: orchestrator (design call)
- status: pending owner confirmation
- Reasoning: Promising can be read on the out-of-sample figures alone, but Works needs a basis not chosen after seeing the result, which the rule can only vouch for with an in-sample period.

## 2026-10-18 | EB H9 (pair spread) | Result side, costs, base and eligibility of a pair
- Question: how is a pair spread judged, what does it charge, what is its base and which pairs count?
- Options: verdict-eligible as a long outcome / diagnostic only like `long_short`; one round trip / two; the base as one value per pair / per name against its sibling; a sibling outside the universe counts / is excluded.
- Decision: results stored and judged as `long_short` (`Outcome.result_side`: Diagnostic only, not paper traded) while the document's `side` stays `long`; `cost_bps` per leg (two round trips) plus borrow on the sibling; the base is every eligible name against its own sibling (a pair twice, once per side), so its hit rate is near one half; a pair needs both legs in the universe at D and each naming the other (`sibling_not_eligible`, `sibling_mismatch`), and an issuer with three or more classes or a class under several ids is AMBIGUOUS, never guessed.
- decided by: orchestrator (design call)
- status: pending owner confirmation
- Reasoning: the spec builds the pair on `long_short` and the owner decision of 2026-10-17 makes a spread diagnostic only, so a pair spread is never a verdict basis unless the owner says so; two legs cost two trades; per-name orientation is the one base that a random side of the pair produces; a one-sided or mismatched pair would pair a name with the wrong class.

## 2026-10-18 | PR #661 review (EB H9) | Pair tests, verdict, and two follow-ups
- Question: where do the pair harness tests live, is a pair spread ever a verdict basis, and are per-reason exclusion counts and a sibling ADV floor in this PR?
- Options: split the test folder now / in the next PR touching it; diagnostic only / verdict-eligible; counts and floor now / follow-up.
- Decision: tests stay in `test_harness_trials.py` (split the folder by kind in the next PR touching it); a pair spread stays Diagnostic only through `result_side`; per-reason exclusion counts (today folded into `excluded_missing`, the reason is on each pick) and an ADV floor on the sibling (short) leg are follow-ups. A reference snapshot without `cik` / `share_class_figi` is MissingDataError, never an empty pair set.
- decided by: orchestrator (design call)
- status: pending owner confirmation
- Reasoning: the architect review found `REFERENCE_FACTS` dropped the ids so every pick read `no_sibling`; the loader now carries them. The folder split and the two counts touch other modules and need their own review.

## 2026-10-18 | PR #661 CI (EB H9) | A reference snapshot without issuer or class ids
- Question: does `share_classes@v1` raise MissingDataError when the reference snapshot has no `cik` / `share_class_figi` column?
- Options: raise / return no rows.
- Decision: no rows (every read is UNKNOWN; a pair pick reads `no_sibling`, counted), reversing the earlier review ask.
- decided by: orchestrator (design call)
- status: pending owner confirmation
- Reasoning: the ingestion nightly end-to-end tests build a reference without those columns and the critical rollups step failed, holding back the workflow; a snapshot built without issuer ids is a normal state, not a broken one.

## 2026-10-18 | EB E2 (PR 667 review) | How the BDC universe is defined
- Question: how is the universe of the BDC price-to-NAV edge defined, when the reference has no BDC type and the SEC company table no SIC for them?
- Options: a ticker list with a maintenance rule / key the list by instrument_id / drop the edge.
- Decision: key by instrument_id: the tickers are resolved once through the SymbolResolver and the ids are committed in the selection preset and the screener (a fitness test keeps them equal); the edge notes say history before the frozen period is survivor-only (BDCs merged away are missing; renamed ones such as ORCC to OBDC 2023 and AINV to MFIC 2022 are the same id). The screener also requires the balance sheet to be at most 135 days old (`rollup.qmj@v1.balance_sheet_age_days`) and discloses that the cover-page share count and the balance-sheet equity can differ by a quarter.
- decided by: orchestrator (design call)
- status: pending owner confirmation
- Reasoning: a ticker is reused and renamed, an id is not (ADR 0018); a list with no maintenance rule is a silent survivor filter, so it is named as one; dropping the edge loses a clean, cheap test of a documented structural niche.

## 2026-10-18 | EB H10b (ensembles and the haircut) | What an ensemble counts as and how its members are treated
- Question: how many trials is a pre-registered grid whose weights are averaged, may a member be the basis, and what does the out-of-sample haircut do?
- Options: every member a trial plus the ensemble / the ensemble once; a member may be promoted as the basis / never; the haircut a verdict gate / a display; one haircut for every edge / a class per edge.
- Decision: the ensemble is one trial (its hash is its members' sorted hashes) with the grid size recorded beside it; members run as role `member`, are reported, never a trial or a basis, and members already logged as screeners stay counted; a member that cannot be weighted leaves the ensemble session out; the haircut is display only, in the run's report (`[oos_haircut] trend = 0.45`, the edge's `oos_class`), not in the read model yet.
- decided by: orchestrator (design call)
- status: pending owner confirmation
- Reasoning: averaging removes the choice among members, which is what multiple-testing counts; letting a member be the basis would restore it (ADR 0065); old logs are never rewritten, so the earlier count only errs conservative; a display keeps the haircut out of the verdict until the owner decides it should gate.

## 2026-10-17 | EB D7 (country CAPE) | Barclays Shiller CAPE file used as personal-use data
- Question: may the stack pull Barclays' public `cape.csv` (26 countries, monthly) although its terms could not be retrieved (the site is a single-page app whose disclaimer text is served only to a browser session)?
- Options: use it as personal research data, one pull a month, no redistribution, no vendor data committed / wait for the owner to read the terms / use Siblis' free tier (8 snapshots, too thin).
- Decision: use it under personal use: `licence = "personal"`, `refetch_days = 28`, tests on a hand-built fixture; the owner confirms the disclaimer once in a browser.
- decided by: Fable on the owner's behalf
- status: final
- confirmed: owner 2026-10-18
- Owner read the disclaimer: personal research use, monthly automated pull, no redistribution, no product built on the index.
- Clause to respect: no reproduction, distribution or transmission without Barclays' consent, so CAPE values and every feature derived from them are never served to other users (`licence = "personal"`, held only by the owners listed in `config/site/users.toml`, ADR 0069).
- Reasoning: the file is public and unauthenticated and has been served for years, a monthly pull is a light use, and the series is optional (the macro step is non-critical), so withdrawing it costs one registry block.

## 2026-10-18 | EB H4 follow-ups | Market-level triggers are a schedule family, not event classes
- Question: should a VIX spike or FOMC date be an event class?
- Options: an event class (base = the universe, N counts per trigger) / a schedule family `on_market:<trigger>` on the 0073 time-series harness.
- Decision: `on_market:<trigger>` (named universe, `base = out_of_window`, benchmark none, one horizon); `market_triggers@v1` in rollups/market, licence personal; FOMC joins as `on_market:fomc`; `tdf_contrarian_flows` stays blocked on `on_market:large_market_month`; amends the time-series schedule rule.
- decided by: orchestrator (design call)
- status: pending owner confirmation
- Reasoning: an event base would equal the universe and each trigger would count once per name.

## 2026-10-18 | EB H4 follow-ups | VIX spike definition and its placement
- Question: how is a VIX spike defined and placed?
- Options: a level only / level plus term-structure inversion; thresholds in config / fixed in the feature.
- Decision: first session with the latest fresh VIX >= 30 and VIX/VIX3M > 1 after >= 21 sessions without one; thresholds fixed in the feature (a change is a version bump); D = the session the reading was first known, both legs FRED `VIXCLS` / `VXVCLS` (`pit = "lag"`, one-day release lag, personal licence), known by D when observation date plus lag is at or before D; a trigger within h sessions of the last counted window is skipped; the base depends on later triggers inside the range (known by range end, never a decision input) and a stretch near range end can change when the range is extended.
- decided by: orchestrator (design call)
- status: pending owner confirmation
- Reasoning: fixed thresholds leave no tuning knob (multiple testing), and the skip rule keeps windows from overlapping.

## 2026-10-18 | EB H4 follow-ups | ipo_lockup and reverse_split classes
- Question: how are lockup expiries and reverse splits read without lookahead?
- Options: the row's instrument_id / CIK mapped through instruments/company as of D; latest version / `latest_versions(through=D)`.
- Decision: CIK mapped through `instruments/company` as of D, `latest_versions(through=D)`, `is_ipo` rows only; `reverse_split` anchored on the ex-date with `ts <= D`, ratio < 1 pinned by a test, funds excluded; `ipo_lockup` sign -1, `announced_ahead`, short avoid-list side.
- decided by: orchestrator (design call)
- status: pending owner confirmation
- Reasoning: a later version or a later instrument mapping would leak survivorship into the entry.

## 2026-10-18 | EB H4 follow-ups | pre_month_end and year_turn windows; weekend and etf_launch skipped
- Question: which calendar windows are added?
- Options: last 3 sessions of the month / turn of the year / weekend / etf_launch.
- Decision: `pre_month_end` (last 3 sessions, names disjoint from `SCHEDULES`) and `year_turn` (last 5 of December + first 5 of January, length 10, belongs to December's year; about 8 windows since 2018 so it cannot reach evidenced); non-overlap property test 2000-2040; weekend skipped (decayed evidence, adds a trial); `etf_launch` deferred until the owner supplies a keyword list.
- decided by: orchestrator (design call)
- status: pending owner confirmation
- Reasoning: each window is one more trial; only those with a documented, undecayed mechanism are worth it.

## 2026-10-18 | EB track E | Owner approvals: shares --force and the stale edge-eval record
- Question: may the owner-approved ops actions run: a forced refetch of every SEC company-facts CIK (`algotrade-ingest shares --force`), and clearing the stale `edge-eval` job record for edge `momentum_12_1` (status running since 2026-10-18T10:00:35Z, no process)?
- Options: wait for the nightly backlog (400 CIKs a night) / run `shares --force` once locally; hand-edit or delete the stale record / clear it only through the jobs service.
- Decision: owner, in the session chat: "run shares --force"; for the stale record: "Approved" (to "clear the stale momentum_12_1 job record through the jobs service"). Bounds: local ingestion through the normal writer, detached, one at a time under the claim lock; no deletes, no `--waive`, no `--force` on anything else, no new vendor calls beyond SEC EDGAR (free, the `shares` task's own pace); the stale record is cleared only through the jobs service (`LocalJobRunner.recover`), never by deleting files by hand.
- decided by: owner
- status: final
- Note: the parent (orchestrating) session ran `shares --force`, not the implementer that recorded this entry; the stale record was cleared by this task through `LocalJobRunner.recover` (kind `edge-eval`, the only running record).
- Reasoning: the statements groups v2/v3/v4 need every CIK refetched: 5,260 CIKs are in the backlog at 400 a night, about 14 nights; `--force` does it in about 40 minutes. The stale record would otherwise block its owner's edge evaluations until the 2 h staleness window, and it is marked failed ("abandoned: the process running it stopped") with a `finished_at`.

## 2026-10-18 | EB track E | Owner approval: CEF coverage while Tiingo Power is active
- Question: may closed-end funds be pulled into coverage (and their history) while the Tiingo Power account is active?
- Options: keep CEFs out of the universe (ADR 0013) / amend coverage to pull CEFs and their history before Tiingo Power ends.
- Decision: owner, in the session chat: "pull cef also until tingo power is there. If the edges is strong we can reconsider our decision to continue tingo power account"
- decided by: owner
- status: final
- Reasoning: `closed_end_fund_discounts` (Strong), `cef_distribution_trap` and `muni_cef_december` are blocked because CEFs are not in universe coverage (ADR 0013). Bars already exist for 330 CEFs (the nightly Massive grouped-daily and Tiingo bars-history from 2010), so the Tiingo cost is 0 symbols; the change is the universe coverage amendment, with no deadline pressure. Continuing the Tiingo Power account is to be reconsidered if the CEF (or other) edges prove strong.

## 2026-10-18 | EB E5 (vol_target) | A volatility-targeted book is scaled down from today's weights over past returns
- Question: how is a book sized to a volatility target without look-ahead, leverage or a hidden re-weighting?
- Options: scale by the stored realised vol of each name / by the book's own daily returns; scale up as well as down / down only; use the returns as stored today / as each day read them; a missing return counts as zero / leaves the session out.
- Decision: sigma is the annualised sample std of `sum(w_i r_i,t)` over `vol_window` (60) sessions ending at D, today's weights on the returns each day `t <= D` read at `t` (through the recording reader, so a restated partition invalidates the legs); `k = min(1, target / sigma)`, names times `k`, the rest cash at the bill yield; a missing return is `no_book_vol`; an all-cash book is not scaled; the target and its window and field join an outcome's hash only when set. The scaled weights go through the turnover pass, so rescaling pays the cost.
- decided by: orchestrator (design call)
- status: pending owner confirmation
- Reasoning: the book's own series captures correlation, which per-name vols do not; down-only keeps the outcome a long, unlevered book; reading each day as it was known keeps a later restatement from moving an earlier session. Architect design of 2026-10-18 (ADR 0074 items 14 to 16 and 18).

## 2026-10-18 | EB E5 (vol_target) | A de-risked book is still judged against the fully invested blend
- Question: when a book holds cash by a volatility target or a canary, is its benchmark scaled the same way or left as the fully invested blend?
- Options: leave the benchmark as written / scale it by the same cash share / add `CASH` as a benchmark constituent on request.
- Decision: leave it: the book is judged against the fully invested blend, so the cost of de-risking shows up as a lower excess return in rising markets; a `CASH` constituent of the benchmark is added only if the owner asks.
- decided by: orchestrator (design call)
- status: pending owner confirmation
- Reasoning: scaling the benchmark by the book's own choices would hide what de-risking cost; the proposed default is the stricter bar. Owner to confirm or overrule.

## 2026-10-18 | EB E5 (macro bridge) | Revised CAPE history is accepted with a caveat
- Question: country CAPE values are revised, so a backfill is not as it was known on each date; is the history used?
- Options: use the history with a caveat in the edge's notes / start the series at the first stored vintage / drop the signal.
- Decision: use it, flagged `revised` with the caveat in the notes of every edge that reads it; a signal built from it is never presented as an as-known test.
- decided by: orchestrator (design call)
- status: pending owner confirmation
- Reasoning: the series is monthly and slow-moving, a vintage-only start would leave years of history empty, and the caveat keeps the limit visible. Owner to confirm or overrule.
## 2026-10-18 | EB E5 (allocation extensions, macro series) | FX 3-month rates and the broad dollar added; two owner calls logged
- Question: which series feed the etf_macro bridge's dollar and FX carry columns, and what does the allocation overlay measure against?
- Options: DTWEXBGS + OECD 3-month interbank rates via FRED (free) / a paid FX source; de-risked book judged against the fully invested blend / against a book with CASH as a constituent; revised CAPE history accepted with a caveat / dropped.
- Decision: add DTWEXBGS (daily, lag 10 days) and the OECD rates for USD, JPY, AUD, CAD and CHF (monthly, lag 60 days), all `pit = "lag"` and open. EUR (IR3TIB01EZM156N) and GBP (IR3TIB01GBM156N) are left out: their last observation is January 2026, so those currencies' `fx_carry` is null until a fresher series is found. Owner decision 1: a de-risked book is still judged against the fully invested blend (CASH becomes a benchmark constituent only if the owner asks). Owner decision 2: the revised CAPE history is accepted for the bridge with a caveat (the backfill is not as-known).
- decided by: orchestrator (design call)
- status: pending owner confirmation
- Reasoning: no paid source is needed; a stale series would make carry look known when it is not; the benchmark stays comparable across edges.

## 2026-10-18 | EB E5 (PR 680 review) | Allocation edges the harness measures only in part
- Question: how are the IBS edge (the source day is close(D) to close(D+1), but S = D + 1 at the earliest), the natgas avoid list and the 9-month lookback filed?
- Options: IBS dropped / filed as a documented-limit variant; natgas against SPY / against the mix of its own funds; a 189-session return column (changes stored group trend_stats@v2) / the 3, 6 and 12 month grid.
- Decision: IBS filed as a documented-limit variant that tests the second-day return, its failure_modes saying the always-held benchmark makes cash days negative by construction; natgas benchmark is the near-equal mix of UNG, USO and DBO, so a positive excess means cash in falling years beat holding them; keep the 3, 6 and 12 month ensemble, no ret_189d (a full-history recompute, catalogue and golden regeneration, every @v2 preset moves; the 9-month return correlates about 0.9 with 6 and 12; a later 4-member grid is a new trial by hash; revisit only if the 3-member ensemble reaches Promising).
- decided by: orchestrator (design call)
- status: pending owner confirmation
- Reasoning: a document that states what it cannot measure is better than none, and a stored-group change for a highly correlated member is cost without information.

## 2026-10-18 | Field guide files: folders by theme group, files split in two
- Question: the twelve `config/site/field_guide/*.toml` files sit at 934-991 lines (the 1000-line cap), so every new entry fails `make filelen`; how is the guide filed?
- Options: raise the cap for these files / split each file in two in place / subfolders named after the four Guide theme groups (tradeable, chart, options, company) with each file split `<stem>.toml` + `<stem>-2.toml` / re-home entries by theme.
- Decision: subfolders by theme group, each file split at an entry boundary near its midpoint (a pure move: no entry changes, no re-homing, since themes interleave across files); the loader reads the folders one level deep and the stem order keeps `x-2` right after `x`, so the order of fields and situations, the drafting prompt bytes and the Builder's help are identical (proved by a before/after snapshot); generated pages move to `docs/data/field-guide/<group>/`, a long theme split into parts under 900 lines; a contract test keeps the layout.
- decided by: orchestrator (design call)
- status: pending owner confirmation
- Note: planned by the architect agent on the owner's behalf; CLAUDE.md's settled line names `field_guide/*.toml`; the owner may reword it to `field_guide/**/*.toml` (this PR does not edit CLAUDE.md).
- Reasoning: the cap is a settled rule, the move costs no behaviour, and the groups are the ones the Guide already shows.
## 2026-10-18 | EB H4 follow-up (ipo_lockup, reverse_split) | Where the lock-up versions and the CIK map are read
- Question: ADR 0075 says read the lock-up table with `latest_versions(through=D)` and map the CIK through `instruments/company` as of D, but a rollup is pure (no storage, no data) and reads its inputs per session.
- Options: a loader that returns the latest version known by each session (`feature_inputs._Versions`, sharing `events.latest_of` with `latest_versions`) / a version filter inside `compute`; the CIK from `instruments/reference` / from `instruments/company` with its `cik` column added to `company_sectors`.
- Decision: the loader dedupes per session by the one shared rule, and `compute` joins the CIK to `instruments/company` of the session (`company_sectors` now returns `cik` too, one more column for its other readers); a CIK with several share classes gives each the event; the nearest lock-up is the earliest expiry from 20 sessions back on.
- decided by: proposed by orchestrator; awaiting owner
- status: pending owner confirmation
- Reasoning: keeps the one version rule in `data/`, keeps the rollup pure, and honours the ADR's company snapshot; the stored reverse-split ratio is new shares per old (a forward 4-for-1 is 4), pinned by a test, a ratio below 1 is a reverse split.

## 2026-10-18 | EB H4 follow-up (ipo_lockup, reverse_split) | Field-guide entries of the new groups sit under the instrument-gates theme
- Question: `events.toml` (977 lines) and the events theme page `docs/data/field-guide/events.md` cannot take 11 more entries (cap 1000 each), the field_guide folder and the docs page folder are both at 12 files, and a new theme would be a 13th page.
- Options: entries under the events theme (fails `make filelen`); a new theme or file (breaks the 12-file cap); the entries under `instrument gates`, whose page has room (the names are avoid-list gates), filed in the files that have room (trend, momentum, options-wing).
- Decision: the third; a structural fix (raise the page cap, or split the events theme) is for the architect.
- decided by: proposed by orchestrator; awaiting owner
- status: pending owner confirmation
- Reasoning: the entries must ship with the columns (coverage test); a mislabelled group is cheaper to move later than a failing gate.

## 2026-10-18 | EB H4 follow-up (PR 700 review) | Dual-class CIKs and the events field-guide split
- Decision: a CIK with two share classes counts the same lock-up expiry twice, which overstates the independent events of an `ipo_lockup` edge: the edge's run record notes it. The events field-guide theme (`events.toml` and its docs page at the cap) needs a sub-folder split; Now / Next is full, so the follow-up is here only.
- decided by: proposed by orchestrator; awaiting owner
- status: pending owner confirmation
## 2026-10-18 | EB E5 (etf_macro bridge) | Field guide entries ship with the first edge that screens on the columns
- Question: does the etf_macro@v1 PR carry field guide entries for its 32 columns?
- Options: entries now (needs a split of the field guide folders, both at their caps) / entries with the folder split or the first edge PR that screens on them.
- Decision: the entries ship with the folder split or the first edge PR that screens on a bridge column; no site preset screens on them yet, so nothing requires one.
- decided by: orchestrator (design call)
- status: pending owner confirmation
- Reasoning: the field guide folders are at their file caps and a guide entry without a user of the field is untestable prose.

## 2026-10-18 | EB E5 (etf_macro bridge) | The bridge fields stay out of the Describe-it prompt
- Question: do the 32 etf_macro@v1 columns enter the natural-language drafting index?
- Options: raise the 13k-token budget / keep the group out of the drafting prompt until an edge screens on it.
- Decision: keep the group out (`services/drafting/prompt.py UNDRAFTED_GROUPS`, a fitness test checks the list and that the prompt honours it); the columns stay in the catalogue, Explore and the Builder. They return to the index, by removing the group from the list, when the first edge screens on them. The budget is not raised.
- decided by: orchestrator (design call)
- status: pending owner confirmation
- Reasoning: the columns apply to about 30 carrier funds and are not for drafts yet; their index lines pushed two golden cases' fields (atr_pct, days_to_earnings) out of the slice.
## 2026-10-18 | EB E5 (canary) | The canary gate reads its signal at D and fails closed
- Question: how does a risk-off gate on a book read its scouts and choose its defensive asset without look-ahead or a silent default?
- Options: read the signal at D / at S; a missing scout counts as positive / leaves the session out; the defensive asset fixed / the highest signal among a declared few; chosen always / only when the gate is on.
- Decision: scouts resolved to ids and the field read at D, never S; the risk-off share is `min(1, bad / breadth)` and the book is `(1 - f) * book + f * defensive`; a missing scout or defensive value is `no_canary:<T>` / `no_defensive:<T>` and leaves the session out; the defensive asset (`CASH`, or the highest signal, ties by ticker) is resolved only when the share is above zero; the canary table is in the outcome hash only when present.
- decided by: orchestrator (design call)
- status: pending owner confirmation
- Reasoning: a signal read at S would trade on the window it is measured over; a missing scout read as positive would be a silent decision to stay invested. Architect design of 2026-10-18 (ADR 0074 item 17).

## 2026-10-18 | EB D6b (Form 4 insider transactions) | The reporting owner's name is stored as filed
- Question: may the insider transaction table store the Form 4 reporting owner's name (`owner_name`), reversing the "no names" part of the PR #651 entry above?
- Options: keep no names (CIK and officer title only) / store the name as filed.
- Decision: store `owner_name` as filed (SEC bulk `RPTOWNERNAME`, Form 4 XML `rptOwnerName`), whitespace trimmed, NULL when absent, never lowercased or altered; a changed spelling across filings is another value, the owner key stays `owner_cik`. Officer and director names are public SEC filing data. Everything else of the #651 entry stands (CIK and officer title as filed, no address, no other identifiers). The name is not part of the row key and never moves a `known_from`. UI rule unchanged: aggregates only, no per-person list unless a screen is explicitly built later.
- decided by: owner
- status: final
- Reasoning: the name is on the public filing beside the CIK that is already stored, so storing it adds no exposure the CIK did not, and it makes the deep-dive dossier and a later per-insider view readable. Reverses only the "no names" clause; the #651 entry's status is `overruled` for that reason.

## 2026-10-18 | Guide Edges web PR | Guide Edges web PR: entry-static-imports waiver and trader-ideas budget
- Question: the Guide Edges web pages (#712) leave the entry static imports 271 B over main's budget (CI 195971 B vs 195700 B, a shared budget that only goes down) and the Ideas page chunk 530 B over main's local size; waive or cut?
- Options: cut elsewhere in the entry / waive the shared rule for this PR and raise by about 300 B.
- Decision: owner waiver of the shared rule for the entry static imports budget only, raised to 196040 B (CI 195971 B + 69 B margin) through the new `waivers` map of perf-budgets.json (the budget script allows that one rise, the PR that adds it); every other budget unchanged. The trader-ideas budget is accepted at 42690 B with its reason; follow-up: diagnose the +530 B (a module moved into the page chunk) in a later PR.
- decided by: owner
- status: final
- Reasoning: the section's lazy drawer loader, paths and kinds and its route must be in the entry; the Edges documents, drawers, pages and route components are already lazy, and the remaining bytes were measured against main.
## 2026-10-18 | EB E5 (batch Y, macro allocation documents) | The gate reads the carrier fund, the macro legs are separate trials, two fields stay undrafted
- Question: how are the volatility-product, curve, credit, CAPE and carry documents filed on the merged bridge, canary gate and vol_target without implying the full source rule?
- Options: a VX column on each volatility fund (a map change and a version bump) / a canary on SPY, the carrier; a macro screener inside the existing ensemble / its own trial; the two new expression features in the Describe-it index / kept out like the bridge group.
- Decision: `vix_roll_yield` holds SVXY only (UVXY and VIXY named and not held, VXX not covered) under a canary on SPY's `vx_basis` (variant `curve_roll`: `vx_roll`), no `oos_class` (one rule, no lookback grid); the macro legs (`credit_spread_below_ma200`, `country_cape_cheapest`, `fx_carry_positive`) are screeners of the existing edges outside their ensembles, so each is one more trial; `bond_curve_timing` ensembles the two slopes; `trend_carry_value_combo` is the ten-country trend plus CAPE slice, carry skipped (no curve history); `vol_managed_equity` is SPY at `vol_target = 0.10`; VAA and DAA are variants of `absolute_momentum_crash_filter` on a 13612W expression feature; `feature.credit_spread_vs_ma200` and `feature.momentum_13612w` join `UNDRAFTED_FIELDS` (two index lines tip the slice margin).
- decided by: orchestrator (design call)
- status: pending owner confirmation
- Reasoning: the carrier fund already holds the VX signal and a map change rewrites a stored group; a grid pre-registered as one ensemble must not absorb a different kind of signal; the bridge group's reason to stay out of the drafting prompt applies to its two derived fields.
## 2026-10-18 | Harness learnings (seven, EB batch) | Brief checklist, live-store authorizations, edge checklist, base fitness test, load guard
- Question: which of the seven learnings from the EB batch become harness changes?
- Options: add each in its most specific home / skip.
- Decision: approved ("approved all 7", relayed by the orchestrating session): worktree path in every brief and `no-automerge` by default for implementers (agent definition + review-and-release); the edge-document checklist (add-screener) and a fitness test `tests/unit/config/site/test_edge_base.py` for the base/picks tautology; live-store authorizations must be the owner's own words in the acting session (review-and-release); `scripts/ops/xdist_workers.py` caps xdist workers to 2 above a load of 12. The auto-merge nudge was already on main (#688).
- decided by: proposed by orchestrator; awaiting owner
- status: pending owner confirmation
- Reasoning: each cost real time in the EB batch (a lost first hour per agent batch, PRs opened without `no-automerge`, eight reviews repeating the same findings, blocked relayed authorizations, runs slowed by load 13+).
## 2026-10-18 | EB H14 batch X (reverse_split_distress_filter) | The short is charged an assumed borrow of 2000 bps a year, not the site's 100
- Question: what borrow does the short side of the reverse-split avoid list pay, when the document itself puts the real borrow at 20 to 100 percent a year?
- Options: (a) keep the site default of 100 bps and note it / (b) a per-edge `borrow_bps_annual = 2000` / (c) an evidence-only short with no verdict basis.
- Decision: (b), 2000 bps a year, worded as a lower bound on the real borrow; the universe is liquid-gated (ADV of $5M or more), so owner decision O2 applies.
- decided by: orchestrator (design call)
- status: pending owner confirmation
- Reasoning: 100 bps on a distressed name flatters the short by an order of magnitude; the low end of the document's own range is the least unrealistic number the store supports.
