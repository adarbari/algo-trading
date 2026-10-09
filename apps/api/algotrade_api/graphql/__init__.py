"""The GraphQL read layer (ADR 0037): the Strawberry schema mounted at ``POST /graphql``, its
scalars (``FeatureName``, ``Date``, ``JSON``), error codes, per-request context and
dataloaders; thin types over ``algotrade.services.read`` live in ``types/``. No logic beyond
``.of()`` mappings, no mutations (writes stay REST).

``schema.py`` builds the schema and the router, ``context.py`` the per-request context,
``loaders.py`` the dataloaders, ``offload.py`` the read pool and its admission control,
``response_cache.py`` the response cache, ``limits.py`` the list-size caps,
``errors.py`` the error codes; the snapshot is ``apps/api/schema.graphql``
(``docs/api/read-model.md``)."""
