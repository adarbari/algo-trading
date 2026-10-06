"""Who is calling (ADR 0040): the ``Authenticator`` protocol and its implementations, Supabase
access tokens verified offline (``supabase``, with the JWKS key cache in ``keys``) and the
loopback-only ``ALGOTRADE_AUTH=off`` mode (``local``), chosen by ``mode.open_authenticator``.
The one place that reads the ``Authorization`` header or decodes a token."""
