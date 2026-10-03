---
name: write-adr
description: Record an architectural decision (new layer, boundary change, storage/vendor/tech choice, superseding an earlier decision). Use whenever a change would contradict or extend docs/architecture.md or an existing ADR.
---

# Write an ADR

1. Copy the format of an existing ADR in `docs/adr/`: Title, **Status** (with date),
   Context, Decision, Consequences. Keep it under a page.
2. Number it with the next free 4-digit number. Name the file `NNNN-short-slug.md`.
3. Superseding a decision? Set the old ADR's status to `superseded by NNNN`; do not delete
   or rewrite it.
4. Add a row to `docs/adr/README.md` (CI checks every ADR is listed).
5. Update whatever it affects: `docs/architecture.md`, specs in `docs/data/` or
   `docs/ui/`, `CLAUDE.md`'s settled-decisions list, `pyproject.toml` import-linter
   contracts, and `docs/roadmap.md`.
6. Run `make check`.
