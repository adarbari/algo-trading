"""Use case: the market regime explained in plain words, on request (ADR 0041, amended
2026-10-06; docs/market-regime-plan.md 5.6). The text model (``services/text_model``, injected
by the API) is given our facts and the allowed links and nothing else; its answer is cleaned
(links outside the list dropped), checked (every number in it must be one of the facts) and
cached per session. Nothing calls the model unasked; the only write is the answer cache."""
