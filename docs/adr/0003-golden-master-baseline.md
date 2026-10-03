# ADR 0003: Golden datasets and a golden-master results baseline

**Status:** accepted

## Context
We want every strategy reviewed constantly, and refactors that silently change results
caught immediately.

## Decision
- Commit a small set of deterministic, checksummed synthetic datasets covering distinct
  market regimes (`datasets/golden/`).
- Commit `benchmarks/baseline.json` containing every metric for every strategy × dataset.
- CI and nightly runs re-evaluate and fail on any diff; changes are accepted only by
  regenerating the baseline in the PR.

## Consequences
- Any behavioural change is visible in review as a JSON diff plus a scorecard.
- Datasets are immutable once published; changes ship as `name_v2`.
