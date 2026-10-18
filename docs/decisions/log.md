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
- status: pending owner confirmation
- Reasoning: the traders' own words (but, except, unless) stay visible and the reading beside them is what they would say; a second negation would read as a double negative.

## 2026-10-17 | PR #589 (Describe it connector) | When the connector token shows
- Question: which joins get a token between part cards?
- Options: every join / only those that change the reading.
- Decision: join "or" and "and_not" always; join "and" only when the words are not a plain conjunction: hidden when every word (commas ignored) is a plain conjunction: and, with, plus, also, then, or there are no words; shown for but, yet, while, although, though, whereas, as long as, so long as, only if, provided (that).
- decided by: orchestrator (design call)
- status: pending owner confirmation
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
- status: pending owner confirmation
- Reasoning: one rule set gives the same reading every time and a wrong reading is one line and one golden case; the owner verifies the cases in the PR. Proposed by the Opus architect in the review; Fable, briefed with the options, confirmed it unchanged: "and" narrows a condition and "or" offers alternatives, the narrower screen costs a few missed names where a wider one buries the idea, and the Builder's plain-English line shows any wrong reading before a save. No golden case changes.

## 2026-10-18 | PR #642 (ADR 0071 PR 6) | Flat fallback when a part cannot sit in a group
- Question: what does a draft do when an "or" or exclusion has a part that is a formula, a missing request, a dropped criterion or words nothing maps?
- Options: keep the draft flat as before groups / group the available sides only.
- Decision: keep it flat; only the formula case gets the verifier's doubt (draft one boolean formula), every other block leaves a visible note ("... is not available, so the 'or' or exclusion is not applied"); two kinds of instrument joined by "or" are doubted (one security_type criterion).
- decided by: Fable on the owner's behalf
- status: pending owner confirmation
- Reasoning: grouping the available sides would silently change the meaning (an "or" side dropped makes the other side mandatory). Proposed by the Opus architect in the review; Fable, briefed with the options, confirmed it and asked that the note say the other conditions apply on their own (done): blocking the draft would throw away the parts that worked.

## 2026-10-17 | PR #644 (E1c option-implied features) | IBKR IV30 change as a personal-licence feature
- Question: does the IV-change edge (c03) get a long-history IBKR variant beside the chain-derived one?
- Options: chain-derived only (history from 2026-10-02) / also `ibkr_iv_chg_5d` and `ibkr_iv_chg_21d` from IBKR's IV30 history (about 502 sessions).
- Decision: add `ibkr_iv_history@v1` with both, `licence = "personal"`, optional like `ibkr_iv@v1`; `cp_iv_history@v1` stays open. Its guide entries say IBKR's IV30 blends calls and puts, so it tests the overall IV-change effect, not the call-minus-put split.
- decided by: orchestrator (design call)
- status: pending owner confirmation
- Reasoning: settled by the architect reviewer of #644 (the format accepts no `architect` decider); the edge can be scored now instead of from November; the read-only broker boundary is untouched (it reads a stored rollup).

## 2026-10-18 | PR #645 (E1b filing_activity) | The 8-K span ends at the previous session
- Question: may `filing_activity@v1.filing_count_5d` count 8-Ks through the session itself?
- Options: through S, with coverage read from row presence / through S-1 (filings known before S-1's close), coverage from the filings walk's `walked_to`.
- Decision: the span ends at S-1 (filings that became known on or before S-1, so accepted before S-1's close, over the 5 sessions ending there; only 8-K and 8-K/A rows), and the value is null unless a clean walk of a session on or before S reached S-1. `feature.news_free_5d` means no 8-K through S-1 and no earnings window in the last 5 sessions.
- decided by: orchestrator (design call)
- status: pending owner confirmation
- Reasoning: the nightly starts about 18:00 New York time and SEC lists 17:30-22:00 acceptances in the next day's index, so S's own 8-Ks are usually unstored when the nightly runs; counting through S read 0 live and 1 on a recompute. The span through S-1 gives the same value live and in a backtest. A history before the first nightly walk reads null. Known limits: the session after a market day EDGAR was closed reads null, and on a SEC-only holiday Friday an after-17:30 acceptance can be missing from the walked index until the next walk.

## 2026-10-18 | PR #651 (D6, Form 4 insider transactions) | Storing the reporting owner's CIK and officer title
- Question: may the insider transaction table store `owner_cik` and `officer_title` (public EDGAR fields that identify a natural person), or only a hashed owner key plus role flags?
- Options: store `owner_cik` + `officer_title` as filed / store a salted hash of the owner CIK + role flags only / store role flags only (no per-person key).
- Decision: store `owner_cik` and `officer_title` as filed, no names, no other identifiers (no address, no owner name from the XML). The table carries the Form 4 public filing data only; the UI shows counts and roles (distinct insiders, officer / director / 10%-owner), never a per-person list. Retention: as the other event grains (indefinite, point-in-time), per D6's plan. `docs/architecture.md` section 10 ("PII: none stored") gets a one-line amendment in a follow-up: "public SEC filer identifiers (reporting-owner CIK, officer title) are stored as filed; no names."
- decided by: Fable on the owner's behalf
- status: pending owner confirmation
- Reasoning: the owner CIK is an SEC public identifier the data set is keyed on; a hash buys nothing (the hash of a public id is trivially reversible against EDGAR) and loses the join to later filings, amendments (4/A) and the deep-dive dossier. Officer title is attribute data a cluster-buy edge weighs (CEO / CFO buys vs. director buys), stored as filed with no name. The cluster-insider-buy edge needs a distinct-insider count, so a stable per-person key is functionally required. Data never enters the public repo (store is local, git-ignored); the read model serves aggregates. Precedent: ADR 0040 keeps emails (private personal data) out of the repo, not public filing data out of the store. Erasure and shorter retention are owner-only decisions (log 2026-10-11), so the default event retention stands until the owner says otherwise.
