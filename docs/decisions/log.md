# Decision log

Append-only, newest last. One entry per product-direction or policy decision, whoever took it
(`.claude/skills/review-and-release`). `decided by`: owner | Fable on the owner's behalf.
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
