---
name: audit-harness
description: Audit the harness (CLAUDE.md, skills, agents, commands, docs they point to) for token waste and contradictions, and report to the owner. Use when /start says the last audit is over 30 days old, when /wrap-up sees CLAUDE.md at 290+ lines, or when asked to audit the harness.
---

# Audit the harness

Read-only until the owner approves. Token figures are chars / 4. Work from `origin/main`.

1. **Measure.** Lines and tokens of `CLAUDE.md` (limit: under 300 lines), the frontmatter of
   every skill and agent (always loaded), and the docs `CLAUDE.md` tells sessions to read.
   Per-section table for `CLAUDE.md`.
2. **Token savings, ranked** by tokens saved x how often loaded: content duplicated in a
   file, a toml or an ADR (point to it instead), tables a `grep` replaces, done history in
   the roadmap, boilerplate repeated across skills. Each row: location (`path:line`),
   proposed change, tokens saved, risk.
3. **Contradictions and drift, verified.** For every suspected conflict open both files and
   cite `path:line` for each side (rules vs ADRs, `CLAUDE.md` vs skills vs Makefile / CI
   config vs code, stale statuses, missing folders or targets: `make -n <target>`, `ls`).
   Label each: confirmed, likely stale, or ambiguous (owner decides). Never report from
   memory.
4. **Split the result:** quick wins (no owner input: wording, stale text, dedupes) versus
   owner decisions (changes the contract with sessions: dropping a rule or table, a settled
   decision, a process gate).
5. **Report to the owner** (table form, short), with the savings after the proposed changes
   and the new `CLAUDE.md` size.
6. **After approval, one harness PR** (worktree `harness/<topic>`, `make changed`, push; CI gates). Record
   the date: update the "Harness audit: last YYYY-MM-DD" line in `docs/roadmap.md` Now / Next.
   Never merge it yourself.
