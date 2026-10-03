---
name: add-feature
description: Add a computed feature (indicator, IV rank, yield, momentum score) to the feature library and nightly pipeline. Use whenever strategies or screeners need a new derived input.
---

# Add a feature

Read first: ADR 0007 and `docs/data/storage.md` (feature grain).

1. **Define it** in `src/algotrade/features/definitions/<group>.py` as `name@v1`, with
   declared inputs (datasets and lookback), output type and grain (per instrument or per
   market).
2. **Pure computation:** inputs in, values out. No I/O. Use only data known as of each
   `ts` (no look-ahead). Pricing maths belongs in `quant/`, not in the feature.
3. **Register it** in the feature registry, so the nightly pipeline and `FeatureView`
   pick it up.
4. **Changing an existing feature's logic?** Create `name@v2`; do not edit v1. Update
   dependents explicitly.
5. **Tests:** known-value unit tests, plus a property test that truncating future data
   does not change past values. If it uses option maths, add `quant` property tests
   (for example put-call parity).
6. **Baseline:** if strategies or screeners use it, run `make baseline` and explain the diff.
7. Run `make check`.
