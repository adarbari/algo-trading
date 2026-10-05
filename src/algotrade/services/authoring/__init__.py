"""Use case: author L4 user configs (ADR 0029). Save / discard a rule screen's draft, finalise
it into an immutable version (validated fail closed), copy a site preset (pinned to its
version) and rebase onto a newer one, and save a named user expression feature. A finalised
screen is on the nightly (ADR 0033). The only package that writes configs; the API calls it."""
