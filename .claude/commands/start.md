---
description: Start a session - check the machine, see what is running, pick up from the roadmap
---

1. Run `make doctor` and `make status` (read-only). If doctor reports a hard failure, say the exact fix it printed.
2. Read only the "Now / Next" section at the top of `docs/roadmap.md`. If its "Harness audit: last" date is more than 30 days before today (or missing), flag it and suggest `/audit-harness`.
3. Summarise in at most 10 lines: machine problems, open PRs and CI, running jobs, the store's latest session, and the top Next items.
4. Ask which item to work on. Do not start work before the answer.
