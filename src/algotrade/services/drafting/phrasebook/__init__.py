"""The phrasebook's structured thresholds in use (ADR 0041; plan: docs/drafting/describe-it-plan.md,
"skip the model when the phrasebook resolves every clause"): ``check.py`` validates the structured
entries against a catalogue, ``resolve.py`` matches a sentence to them and returns the criteria
when they cover every word of it. Pure; no model, no storage."""
