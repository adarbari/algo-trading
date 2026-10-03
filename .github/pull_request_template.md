## What & why

## Checklist
- [ ] `make check` passes locally
- [ ] New code has unit tests in the mirrored `tests/unit/<layer>/` folder
- [ ] No layer boundary changes (or `pyproject.toml` contracts + `docs/architecture.md` updated with an ADR)
- [ ] If `benchmarks/baseline.json` changed: the scorecard diff is explained below and is intended
- [ ] New strategy? Registered in `strategies/registry.py`, passes property tests, beats `buy_and_hold` somewhere meaningful (not only on `random_walk`)

## Baseline / scorecard changes
<!-- Paste the relevant rows of the scorecard before/after, or "none". -->
