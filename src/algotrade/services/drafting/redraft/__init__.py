"""Re-draft one part of a Describe-it draft (ADR 0041, amended 2026-10-12): the trader retypes
the words of one explained part, the model is asked about those words alone (a scoped prompt),
and the answer is merged into the draft the browser holds. ``request`` re-validates what the
browser sends, ``prompt`` builds the scoped prompt, ``merge`` replaces the part's rows and
keeps the other parts', ``run`` is the one use case and ``cap`` the per-user daily limit."""
