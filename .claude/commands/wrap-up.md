---
description: End a session - propose harness learnings, update the roadmap's Now / Next, hand off
---

1. Run `.claude/skills/capture-learning` over this session's candidates (owner corrections
   and preferences, errors a rule would have prevented). Show the owner the proposed list;
   open the harness PR only after they approve.
2. Update the "Now / Next" section of `docs/roadmap.md` for anything this session opened,
   closed or left running (PR numbers, detached jobs and their status files).
3. If `wc -l CLAUDE.md` is 290 or more, run `.claude/skills/audit-harness` (report to the owner first).
4. Summarise in at most 8 lines: what merged, what is open, what is running, what the next
   session should pick up.
