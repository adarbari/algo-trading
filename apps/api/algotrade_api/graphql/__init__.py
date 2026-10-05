"""The GraphQL read layer (ADR 0037): the Strawberry schema mounted at ``POST /graphql``, its
scalars (``FeatureName``, ``Date``, ``JSON``), error codes, per-request context and
dataloaders; thin types over ``algotrade.services.read`` live in ``types/``. No logic beyond
``.of()`` mappings, no mutations (writes stay REST).

Empty until read-model PR 4 (``docs/api/read-model.md``)."""
