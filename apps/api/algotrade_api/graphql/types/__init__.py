"""GraphQL object types, one module per domain read object (ADR 0037): fields copied from the
read dataclass by one ``.of()`` classmethod, resolvers that call one loader or dataloader and
wrap the result. Never pandas or ``algotrade.data``."""
