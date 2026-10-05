"""GraphQL object types, one module per domain read object (ADR 0037): fields copied from the
read dataclass by one ``.of()`` classmethod, resolvers that call one loader or dataloader and
wrap the result. Never pandas, ``algotrade.data`` or ``services.explore``.

Empty until read-model PR 4 (``docs/api/read-model.md``)."""
