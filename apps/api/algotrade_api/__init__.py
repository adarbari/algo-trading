"""The API app (ADRs 0024, 0037): the web app's only backend. Page reads are GraphQL over the read
model (``graphql/``, ``algotrade.services.read``); REST is writes, job polling, health, live
quotes and preview POSTs. ``main`` builds the app, ``routes/`` holds one router per area,
``schemas/`` the response models (the public contract: OpenAPI -> the generated TS client),
``deps`` the request dependencies and ``cli`` the ``algotrade-api`` entry point."""

from algotrade.config.env import arrow_system_pool

# Arrow's C++ code allocates from its own default pool, which only the environment variable (read
# when pyarrow is first imported, so before anything else of the app is) keeps off mimalloc.
# ``algotrade_api`` is the first package any API entry point imports; the launchd agents need no
# change (docs/perf/api-memory.md).
arrow_system_pool()

__version__ = "0.1.0"
