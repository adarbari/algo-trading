"""Use case: a rule screen drafted from a sentence (ADR 0041). A text model (``TextModel``,
injected by the API; never a vendor import here) maps the sentence onto the caller's field
catalogue; the answer is parsed strictly, invented fields are dropped with a reason and the rest
is validated as finalise would. The result is a draft document for the Builder: never a write,
never a run."""
