"""The API app (ADR 0025): a read-only FastAPI over ``algotrade.services.explore``, the web
app's only backend. ``main`` builds the app, ``routes/`` holds one router per area,
``schemas/`` the response models (the public contract: OpenAPI -> the generated TS client),
``deps`` the request dependencies and ``cli`` the ``algotrade-api`` entry point."""

__version__ = "0.1.0"
