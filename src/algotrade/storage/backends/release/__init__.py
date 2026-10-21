"""The serving release store (ADR 0077): derived, immutable per-session snapshots (a manifest and
small Parquet tables) beside the data store, built in a draft that pins its commit sequence,
sealed, and served through one atomic CURRENT. A derived cache like the history copy: deleting
it loses nothing."""
