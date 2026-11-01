"""``listing_resolver``: ticker -> ``instrument_id`` as of a day, from the listing history, for a
filing that names its issuer by ticker only (SEC Form 4, EB D6).

The listing history is one full copy per pull session, so the read takes its latest snapshot (the
identity exception of ``universe``): what each listing was CALLED and when it was listed. Point in
time is kept by the dates, not the snapshot: ``SymbolResolver.from_listings`` maps a ticker to the
listing whose dates contain the day (a recycled ticker is two ids by date; a delisted issuer keeps
its own) and a ticker no listing of that day carries is unknown, never today's holder. The
resolver of one day is built once and kept (a backfill asks the same few hundred days thousands of
times); ``MissingDataError`` when no listing history is stored."""

from collections.abc import Callable
from datetime import date

from algotrade.data.listings.universe import listing_frame
from algotrade.data.resolver import SymbolResolver
from algotrade.storage.tables.readers import StoreReader


def listing_resolver(reader: StoreReader) -> Callable[[date], SymbolResolver]:
    """A function from a day to the resolver of the listings alive on it."""
    listings, _ = listing_frame(reader)
    kept: dict[date, SymbolResolver] = {}

    def on(day: date) -> SymbolResolver:
        if day not in kept:
            kept[day] = SymbolResolver.from_listings(listings, day)
        return kept[day]

    return on
