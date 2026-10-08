---
name: capture-learning
description: Turn a lesson from this session (an owner correction or preference, or an error a rule would have prevented) into a harness change, placed in its most specific home and checked against existing rules so nothing contradicts. Use at a natural break (before opening a PR, or when the owner wraps up) whenever a candidate learning was noted; also run by /wrap-up.
---

# Capture a learning into the harness

**Noting is automatic; changing the harness needs the owner's approval.**

## While working: note candidates (no edits yet)

Note a candidate the moment one of these happens:

- The owner corrects you, rejects an approach, or states a preference ("always…", "never…",
  "I'd rather…").
- A check, CI job or reviewer catches something a written rule would have prevented.
- You lose real time to setup or environment trouble the next session would repeat.
- The owner brings an issue to fix (a failed nightly step, a wrong page value, a bad
  email). The first candidate is always **the missing test**: name the unit, contract or
  fitness test that would have caught it during implementation, add it with the fix (it
  fails before, passes after) and put it first in the PR description. Prefer a fitness
  test over config or a contract test over a workflow to a one-off regression test. A
  rule is a candidate only when no test can enforce it (CLAUDE.md Code rules, 4).

Each candidate is one line: what happened → the rule that would have prevented it. Keep
working; do not edit the harness mid-task.

## At a natural break: propose

Before opening the PR (or when the owner wraps up), for each candidate:

1. **Is it worth a rule?** Skip one-offs, anything tied only to this task, and anything a
   check already enforces. A rule must apply to future sessions.
2. **Search for what already exists.** `grep -rn` the topic across `CLAUDE.md`,
   `.claude/skills/`, `.claude/agents/`, `.claude/commands/`, `docs/` and `docs/adr/`.
3. **Classify it against what you found:**
   - *Already covered* → drop it (or sharpen the existing wording if it was ambiguous).
   - *Overlaps* → edit the existing rule in place; never add a second rule on the same topic.
   - *Contradicts a settled decision or ADR* → not a harness edit: it needs an ADR
     (`.claude/skills/write-adr`) and the owner's decision. Flag it; do not add it.
   - *New* → add it.
4. **Pick the most specific home**, one place only (elsewhere gets at most a pointer):
   the matching skill > an agent definition > the area's doc in `docs/` > `CLAUDE.md`.
   `CLAUDE.md` is capped at 300 lines (fitness test): only cross-cutting rules go there,
   as one line.
5. **Prefer enforcement over prose.** If a test, lint rule or fitness check can enforce it,
   propose that instead of (or with) the wording.
6. **Show the owner** a short list: each learning, its classification, its home and the
   exact wording. Push nothing until they approve; then one harness PR
   (`scripts/worktree.sh`, `make changed`, push; CI gates), never mixed into feature work.
