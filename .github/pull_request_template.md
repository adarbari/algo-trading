## What & why

## Checklist
- [ ] `make check` passes locally
- [ ] Fits the target architecture (`docs/architecture.md`) and existing ADRs, or a new ADR is included
- [ ] New code has unit tests in the mirrored `tests/unit/<layer>/` folder
- [ ] No layer boundary changes (or `pyproject.toml` contracts + `docs/architecture.md` updated with an ADR)
- [ ] Data: keyed by `instrument_id`, point-in-time columns present, no paths built outside `storage/backends/`
- [ ] Backtests and screeners read only from stores (no vendor calls)
- [ ] UI: only `@algotrade/ui` components used; new components added to the design system with story + test + snapshot
- [ ] If `benchmarks/baseline.json` changed: the scorecard diff is explained below and is intended
- [ ] New strategy? Registered, passes property tests, beats `buy_and_hold` somewhere meaningful (not only on `random_walk`)

## Baseline / scorecard changes
<!-- Paste the relevant rows of the scorecard before/after, or "none". -->
