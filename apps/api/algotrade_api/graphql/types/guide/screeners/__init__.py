"""GraphQL types of the Guide's Screeners section (mirrors ``services/read/guide/screeners``,
ADR 0051): ``GuideScreenerIndex`` (the lead page with a card per family),
``GuideScreenerCategory`` (a family's page with its screeners as rows) and
``GuideScreenerDetail`` (one screener's page); each mirrors a read dataclass through one
``.of()``. Session-free."""
