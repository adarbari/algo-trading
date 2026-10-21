"""The serve-release workflow (ADR 0077 decision 4): build, promote and prune the serving
release under the ``serve`` lock, with its own run record. Started after a nightly or a
post-session finishes and by ``algotrade-ingest serve-release``; never a step of the nightly."""
