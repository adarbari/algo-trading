"""GraphQL types at market grain (mirrors ``services/read/market`` and ``services/read/regime``,
ADR 0047): ``Market`` (its values by catalogue name and the history of its stored fields) and
``MarketRegime`` with its scores, indicator cards, sizing rule, label bands, reference episodes
and NBER recessions; each mirrors a read dataclass through one ``.of()``."""
