"""The owner's review lists for the Admin workspace (``/admin/review/*``): listings marked for
FIGI review and ETFs whose leverage the rules could not classify.

Admin reads stay REST until read-model PR 10 moves them to ``services/read/ops`` (they lived in
``explore/universe.py`` until PR 7 moved the universe table to the read model)."""

from dataclasses import dataclass
from datetime import date
from typing import Any

from algotrade.data.reference import instruments
from algotrade.services.explore.store import NotFoundError, ReadStore, partition_for, records

REFERENCE = "instruments/reference"
UNIVERSE_BUILD = "universe_build"  # the job that records the FIGI review list in its stats


@dataclass(frozen=True)
class ReviewList:
    session: date | None
    source: str  # where the rows come from: a run id, or the reference snapshot
    items: list[dict[str, Any]]


def figi_review(store: ReadStore) -> ReviewList:
    """Listings marked for FIGI review, as the latest universe build recorded them; without
    such a record, the marked rows of the latest reference snapshot."""
    for run in reversed(store.reader.runs(UNIVERSE_BUILD)):
        if "figi_review" in run.stats:
            return ReviewList(run.session_date, run.run_id, list(run.stats["figi_review"]))
    session = partition_for(store.reader, REFERENCE, None)
    ref = instruments(store.reader, session)
    if "vendor_figi" not in ref.columns:
        return ReviewList(session, REFERENCE, [])
    marked = ref[ref["status"].eq("ACTIVE") & ref["vendor_figi"].notna()].sort_values("symbol")
    columns = ["symbol", "instrument_id", "figi", "vendor_figi", "figi_review_since"]
    return ReviewList(session, REFERENCE, records(marked.reindex(columns=columns)))


def leverage_review(store: ReadStore, on: date | None = None) -> ReviewList:
    """Active ETFs whose leverage the rules could not classify (``leverage_source`` =
    ``needs_review``: UNKNOWN until curated in ``config/site/overrides``)."""
    session = partition_for(store.reader, REFERENCE, on)
    ref = instruments(store.reader, session)
    if "leverage_source" not in ref.columns:
        raise NotFoundError(f"{REFERENCE} {session}: no leverage classification stored")
    pending = ref[ref["leverage_source"].eq("needs_review") & ref["status"].eq("ACTIVE")]
    columns = ["symbol", "instrument_id", "name", "security_type", "exchange"]
    return ReviewList(session, REFERENCE, records(pending.sort_values("symbol")[columns]))
