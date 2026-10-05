"""The owner's review lists for the Admin pages (``ReviewList``): listings marked for FIGI review,
and ETFs whose leverage the rules could not classify.

Curation lists over the reference snapshot the session sees (``Session.referenceSnapshot``,
ADR 0007's one rule); the FIGI list as the universe build on or before the session recorded it
in its run stats (a run record), else the marked rows of that snapshot."""

from dataclasses import dataclass
from datetime import date
from typing import Any

import pandas as pd

from algotrade.core.model.errors import MissingDataError
from algotrade.core.model.fields import REFERENCE_TABLE
from algotrade.data.reference import instruments
from algotrade.services.read.context import ReadContext
from algotrade.services.read.values import stored_values

UNIVERSE_BUILD = "universe_build"  # the job that records the FIGI review list in its stats
FIGI_COLUMNS = ("symbol", "instrument_id", "figi", "vendor_figi", "figi_review_since")
LEVERAGE_COLUMNS = ("symbol", "instrument_id", "name", "security_type", "exchange")


@dataclass(frozen=True)
class ReviewList:
    """Rows to review: ``session`` the snapshot or run they come from (None: nothing stored),
    ``source`` a run id or the reference table, ``items`` one row each."""

    session: date | None
    source: str
    items: tuple[dict[str, Any], ...]


def _reference(ctx: ReadContext) -> pd.DataFrame | None:
    """The reference snapshot the session sees (``None``: none stored)."""
    try:
        return instruments(ctx.reader, ctx.session.date)
    except MissingDataError:
        return None


def _rows(frame: pd.DataFrame, columns: tuple[str, ...]) -> tuple[dict[str, Any], ...]:
    ordered = frame.sort_values("symbol").reindex(columns=list(columns))
    return tuple(stored_values(r) for r in ordered.to_dict("records"))


def load_figi_review(ctx: ReadContext) -> ReviewList:
    """Listings marked for FIGI review, as the universe build for the session recorded them (the
    latest on or before it, ADR 0007's rule, disclosed as ``session``; never a later build);
    without such a record, the active rows of the session's reference snapshot with a vendor
    FIGI."""
    day = ctx.session.date
    builds = ctx.reader.runs(UNIVERSE_BUILD)
    recorded = [r for r in builds if r.session_date <= day and "figi_review" in r.stats]
    if recorded:  # the build for the session, else the last one before it (never a later one)
        run = max(recorded, key=lambda r: (r.session_date, r.started_at))
        return ReviewList(run.session_date, run.run_id, tuple(run.stats["figi_review"]))
    ref = _reference(ctx)
    snap = ctx.session.reference_snapshot
    if ref is None or "vendor_figi" not in ref.columns:
        return ReviewList(snap, REFERENCE_TABLE, ())
    marked = ref[ref["status"].eq("ACTIVE") & ref["vendor_figi"].notna()]
    return ReviewList(snap, REFERENCE_TABLE, _rows(marked, FIGI_COLUMNS))


def load_leverage_review(ctx: ReadContext) -> ReviewList:
    """Active ETFs whose leverage the rules could not classify (``leverage_source`` =
    ``needs_review``: UNKNOWN until curated in ``config/site/overrides``), in the session's
    reference snapshot; empty when the snapshot has no leverage classification."""
    ref = _reference(ctx)
    snap = ctx.session.reference_snapshot
    if ref is None or "leverage_source" not in ref.columns:
        return ReviewList(snap, REFERENCE_TABLE, ())
    pending = ref[ref["leverage_source"].eq("needs_review") & ref["status"].eq("ACTIVE")]
    return ReviewList(snap, REFERENCE_TABLE, _rows(pending, LEVERAGE_COLUMNS))
