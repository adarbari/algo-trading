"""The phrasebook's structured thresholds in use (ADR 0041; plan: docs/drafting/describe-it-plan.md,
"skip the model when the phrasebook resolves every clause"): ``check.py`` validates the structured
entries against a catalogue, ``resolve.py`` matches a sentence to them and returns the criteria
(and where each entry's words are) when they cover every word of it, ``shortcut.py`` turns that
into the answer ``draft_screen`` serves without the model. Pure; no model, no storage."""
