---
name: review-and-release
description: Review and release a PR: the architect review loop, the policy gate (owner in the session, else a Fable agent on the owner's behalf, always logged in docs/decisions/log.md), and when the orchestrating session removes no-automerge. Use for every PR an implementer opened with no-automerge, and whenever a reviewer or hand-back lists "Owner decisions".
---

# Review and release a PR

**Default (owner decision 2026-10-11):** a PR with no product-direction or policy decision
releases after the Opus reviewer's `Re-review: no` and green CI, with no owner input and no
owner click. The owner is involved only for policy or product decisions: asked in the
session, else decided by a Fable agent on their behalf, and always logged.

## 1. Open and review

1. The implementer opens the PR with `no-automerge` (architect-area change) and hands back,
   listing any unresolved owner decisions (it never decides them).
2. The orchestrator sends the diff to the `architect` (Opus) with a focus list. The report
   ends with `Owner decisions:` (policy only, each with options and a recommendation), then
   `Re-review: yes | no`.
3. The implementer fixes the findings and hands back a per-finding list (finding -> commit or
   `path:line` -> test). The orchestrator sends it to the same reviewer (SendMessage). Repeat
   while the reviewer answers `Re-review: yes`.

## 2. The policy gate

**Who decides what** (owner decision 2026-10-11; this is the one list, `architect.md` and
`implementer.md` cite it):

- **Design and engineering calls** (thresholds, test structure, refactor order, naming,
  mechanics): the orchestrating session and the reviewer settle them. Logged, when worth a
  line, as `orchestrator (design call)`.
- **Policy**: who sees what; what personal data is stored, for how long, its retention and
  erasure rules; money or the budget; what the product does or shows users (a new screen, a
  behaviour choice, scope); a contradiction of an ADR; anything the reviewer marks as the
  owner's. The orchestrating session never decides these: the owner in the session, else (owner
  away) a Fable agent on their behalf.
- **Owner only** (Fable may not decide): spending above existing caps, deleting or erasing
  data, security or permission settings, publishing outside the repo, merging with failing CI,
  overriding an ADR. The PR stays `no-automerge` plus `needs-owner`.

Whenever a policy decision is open, the orchestrator ADDS `needs-owner` to the PR (it removes
only the label it set, once the decision is logged), so `scripts/auto_merge.sh` blocks the merge
mechanically.

For a policy decision:

- **Owner present**: ask in the session with `AskUserQuestion`: one clear question, options
  with consequences, a recommendation. Keep working on other items meanwhile.
- **Owner away** (said so, or no answer once all other work is done): brief a Fable agent
  (`model: "fable"`: the decision, the options, the constraints, the relevant ADRs), apply its
  answer, and log it as `Fable on the owner's behalf`, status `pending owner confirmation`.

Every policy decision, by the owner or Fable, is appended to `docs/decisions/log.md` (in this
PR or a harness PR) and listed in the PR body with its source. `/start` shows entries pending
confirmation; the owner confirms or overrules by telling the session, which updates the entry's
`status` line to `final` with `- confirmed: owner YYYY-MM-DD` (an overrule means a follow-up
PR). Only the owner's word makes an entry `final`; an agent never does.

## 3. Release

When the reviewer's last verdict is `Re-review: no`, CI on the head is green, the PR has no
`needs-owner` label (added for every open policy decision), no policy decision is unanswered, and the PR body lists the decisions taken (owner, or Fable on the
owner's behalf), the **orchestrating session** removes `no-automerge` from PRs created in its
own flow (an implementer's label counts as its orchestrator's). The auto-merge workflow then
merges on green; never `gh pr merge`. The sweep runs on CI completion and every 30 minutes, not on label events, so right after removing the label run `gh workflow run auto-merge.yml` (the sanctioned nudge; it only sweeps). Post a short PR comment: reviewer rounds and decisions.

- A PR with an open owner decision stays `no-automerge`.
- `needs-owner` is the explicit "owner must look" label (e.g. a requested visual review);
  never remove it. `scripts/auto_merge.sh` skips a PR carrying it, as it skips `no-automerge`.
- Push rules are unchanged (rule 9: `make changed`, merge origin/main right before, never
  force-push).
