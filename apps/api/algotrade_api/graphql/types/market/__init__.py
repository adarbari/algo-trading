"""GraphQL types at market grain (mirrors ``services/read/market`` and ``services/read/regime``,
ADR 0047): ``Market`` (its values by catalogue name) and ``MarketRegime`` with its scores,
indicator cards, sizing rule and label bands; each mirrors a read dataclass through one
``.of()``."""
