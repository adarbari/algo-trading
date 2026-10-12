"""Use case: the explained parts of a draft (ADR 0041, amended 2026-10-11): the trader's sentence
split into the parts the model says it read, each part's words located in the sentence by the
server, every item of the answer (criterion, formula, missing feature, ambiguous term, suggestion,
the rank) attributed to a part deterministically, the part's kind decided from what it holds and
its reading checked against its numbers. Pure over the answer and the sentence; writes nothing
(split from services/drafting, at its module cap)."""
