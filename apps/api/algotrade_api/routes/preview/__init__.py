"""Dry-run routes over unsaved Builder input (ADR 0029): each takes a POST body, calls one
``services.preview`` query over the request's ``ReadContext`` and saves nothing."""
