"""The API app (ADRs 0024, 0037): the web app's only backend. Page reads are GraphQL over the read
model (``graphql/``, ``algotrade.services.read``); REST is writes, job polling, health, live
quotes and preview POSTs. ``main`` builds the app, ``routes/`` holds one router per area,
``schemas/`` the response models (the public contract: OpenAPI -> the generated TS client),
``deps`` the request dependencies and ``cli`` the ``algotrade-api`` entry point."""

__version__ = "0.1.0"
