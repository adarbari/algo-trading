# Decision log

Append-only, newest last. One entry per product-direction or policy decision, whoever took it
(`.claude/skills/review-and-release`). `decided by`: owner | Fable on the owner's behalf | orchestrator (owner present) | orchestrator (owner away).
`status`: final | pending owner confirmation | overruled. The owner confirms or overrules by
telling the session, which updates the entry (an overrule means a follow-up PR).

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
- Decision: the replay test skips a case with `recorded: false` for 14 days; after that a fitness test fails.
- decided by: orchestrator (owner present)
- status: pending owner confirmation
- Reasoning: CI must not go red on the PR that adds a curated case, but cases must not stay unrecorded.

## 2026-10-11 | PR #535 | Prompt budget
- Question: how does the drafting prompt stay inside its token budget?
- Options: shorten field-detail descriptions / cap backlog keys and shorten examples.
- Decision: field-detail descriptions stay at 160 chars (restored); open backlog keys in the prompt are capped at 8, relevance first; the second worked example is shortened; the budget test pads the keys to the cap. The margin is about 77 tokens, so a retrieval trim PR comes before any further prompt text.
- decided by: orchestrator (owner away)
- status: pending owner confirmation
- Reasoning: taken following two Opus reviews.

## 2026-10-11 | PR #535 | Split services/drafting
- Question: when is the full `services/drafting` folder (9 of 10 modules) split?
- Options: inside #535 / a separate refactor PR after #535 merges.
- Decision: split into `contract/` and `golden/` subfolders in a separate refactor PR after #535 merges.
- decided by: orchestrator (owner away)
- status: pending owner confirmation
- Reasoning: keeps #535 reviewable.

## 2026-10-11 | PR #540 | Retention of curated golden cases
- Question: which events does a curated golden case spare from retention?
- Options: only its final event / the whole chain.
- Decision: a curated golden case spares the whole chain (every event id in `source_events`), not only its final event.
- decided by: orchestrator (owner away)
- status: pending owner confirmation
- Reasoning: the stored iteration stays whole.

## 2026-10-11 | PR #535 | API shape of the formula dry run
- Question: what does REST serve of `FormulaDryRun`, and which type is `Alternative.label`?
- Options: serve `missing` / withhold it; `label` as enum / text.
- Decision: `FormulaDryRun.missing` is not served over REST; `Alternative.label` is `text` in the API.
- decided by: orchestrator (owner away)
- status: pending owner confirmation
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
