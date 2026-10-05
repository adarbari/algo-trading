"""Read-only dry runs of unsaved Builder input (ADR 0029), over the request's ``ReadContext``: a
draft rule screen previewed on the context's session with the nightly evaluator, and a formula
type checked and sampled. Nothing here writes; the API serves them as POSTs (REST by design)."""
