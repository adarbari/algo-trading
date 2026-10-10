"""The reads of the edge harness that are made once per decision session, whatever the horizon or
the edge variant (ADR 0053, ADR 0063): ``SessionReads`` caches each screener's run, the regime
label, the eligible names per universe, the implied vol and the scored outcomes until a chunk of
sessions is released; ``implied_at`` reads the implied vol of names at one session, for the
harness and the paper record alike."""

from collections.abc import Callable, Iterable
from contextlib import AbstractContextManager
from datetime import date
from typing import TYPE_CHECKING

import pandas as pd

from algotrade.config.strategy.schema import Selection
from algotrade.core.model.errors import MissingDataError
from algotrade.core.model.fields import REFERENCE_TABLE
from algotrade.core.views.market_features import MARKET_FEATURES
from algotrade.data import StoreReader
from algotrade.data.listings.membership import TABLE as MEMBERSHIP_TABLE
from algotrade.data.listings.universe import TABLE as LISTING_TABLE
from algotrade.data.reference import UNIVERSE_TABLE
from algotrade.services.evaluation.cross_section.historical import (
    HistoricalCaveat,
    IdentityTally,
)
from algotrade.services.evaluation.cross_section.legs.rows import DayReads
from algotrade.services.evaluation.cross_section.picks import (
    RankedRun,
    SelectionReads,
    screen_variant,
)
from algotrade.services.screening.regime import session_market
from algotrade.services.selection import fields_view

if TYPE_CHECKING:
    from algotrade.services.evaluation.cross_section.harness import Variant

UNKNOWN = "UNKNOWN"
# Not an input table a screener lacks for a session but the run's own wiring (market features
# not loaded, no universe or reference snapshot): always an error, never a lost session.
WIRING_DATASETS = (
    MARKET_FEATURES,
    UNIVERSE_TABLE,
    REFERENCE_TABLE,
    LISTING_TABLE,
    MEMBERSHIP_TABLE,
)


class SessionReads:
    """What is read once per decision session, whatever the horizon or the edge variant: each
    screener's run and the regime label; per universe the eligible names (scopes sharing one
    universe read it once), the implied vol when the measure needs it (per ``iv_field`` and
    eligible names) at D and each scope's scored outcomes (``outcomes``). ``release``
    drops all of it (after a chunk of sessions): only the universe snapshot dates and the
    sessions a screener could not be run on (``lost``: its missing table) are kept. It reads
    through a recording reader: what a session reads inside ``attribute(day)`` is logged against
    that day (``day_reads``, ADR 0063)."""

    def __init__(self, reader: StoreReader, label_field: str):
        self._reader, self._label_field = reader.recording(), label_field
        self._selections = SelectionReads(self._reader)
        self._runs: dict[tuple[str, date], RankedRun | None] = {}
        self._eligible: dict[tuple[str, date], frozenset[str]] = {}  # (universe repr, D)
        self._labels: dict[date, str] = {}
        self._implied: dict[tuple[str, frozenset[str], date], dict[str, float | None]] = {}
        self._outcomes: dict[tuple[str, int, date], pd.DataFrame] = {}
        self._snapshots: set[date] = set()
        self._identity = IdentityTally()
        self.errors: dict[str, MissingDataError] = {}  # variant -> its first lost session's error
        self.lost: dict[tuple[str, date], str] = {}  # (variant, D) -> the table it had no data in

    def attribute(self, day: date) -> AbstractContextManager[None]:
        """Log the reads made inside the block against the decision session ``day``."""
        return self._reader.attribute(day)

    def day_reads(self, day: date) -> DayReads:
        """What ``day`` read: its logged partitions, the commit sequence at its first read and
        the historical-identity counts of its eligible and screened names."""
        return DayReads(
            day,
            self._reader.reads(day),
            self._reader.inputs_seq(day),
            self._identity.of("eligible", day),
            self._identity.of("screened", day),
        )

    def attributed_days(self) -> list[date]:
        return self._reader.attributed_days()

    def snapshot_of(self, variant: "Variant", day: date) -> date | None:
        """The universe snapshot the screener's run at ``day`` read (None: no run)."""
        found = self._runs.get((variant.id, day))
        return None if found is None else found.snapshot

    def run(self, variant: "Variant", day: date) -> RankedRun | None:
        """The screener's run at ``day``; None when an input table has no data for it (the
        session is lost to this screener, counted, never a miss)."""
        if (variant.id, day) not in self._runs:
            self._runs[variant.id, day] = self._screen(variant, day)
        return self._runs[variant.id, day]

    def _screen(self, variant: "Variant", day: date) -> RankedRun | None:
        try:
            found = screen_variant(self._reader, variant.config, day)
        except MissingDataError as error:
            if error.dataset in WIRING_DATASETS:  # not an input the screener lacks: a broken run
                raise
            self.lost[variant.id, day] = error.dataset
            self.errors.setdefault(variant.id, error)
            return None
        self._snapshots.add(found.snapshot)
        self._identity.note("screened", day, found.identity)
        return found

    def eligible(self, universe: Selection, day: date) -> frozenset[str]:
        key = (repr(universe), day)  # scopes with the same universe share one read
        if key not in self._eligible:
            found = self._selections.eligible(universe, day)
            self._identity.note("eligible", day, found.identity)
            self._eligible[key] = found.ids
        return self._eligible[key]

    def caveat(self) -> HistoricalCaveat | None:
        """What the sessions read before the first reference snapshot covered (None: none)."""
        return self._identity.caveat()

    def snapshots(self) -> list[date]:
        """The universe snapshot dates the screens read."""
        return sorted(self._snapshots)

    def release(self) -> None:
        """Forget what was read for the sessions done (memory stays flat in the sessions)."""
        self._runs.clear()
        self._eligible.clear()
        self._labels.clear()
        self._implied.clear()
        self._outcomes.clear()

    def label(self, day: date) -> str:
        if day not in self._labels:
            name = self._label_field
            value = session_market(self._reader, [name], day).get(name)
            self._labels[day] = UNKNOWN if value is None else str(value)
        return self._labels[day]

    def implied(self, field_name: str, ids: frozenset[str], day: date) -> dict[str, float | None]:
        key = (field_name, ids, day)
        if key not in self._implied:
            self._implied[key] = implied_at(self._reader, field_name, ids, day)
        return self._implied[key]

    def outcomes(
        self, scope: str, horizon: int, day: date, score: Callable[[], pd.DataFrame]
    ) -> pd.DataFrame:
        """``score()`` once per (scope, horizon, D) in a chunk: every screener, baseline and the
        random draws of a scope score the same outcome rows (the frame is never changed)."""
        key = (scope, horizon, day)
        if key not in self._outcomes:
            self._outcomes[key] = score()
        return self._outcomes[key]


def implied_at(
    reader: StoreReader, field_name: str, ids: Iterable[str], day: date
) -> dict[str, float | None]:
    """The implied vol ``field_name`` of ``ids`` read at the decision session ``day`` (None: not
    stored): what an ``expires_otm`` strike or a vol ratio is measured from, for the harness and
    the paper record alike."""
    wanted = sorted(ids)
    view, _ = fields_view(reader, (field_name,), day, wanted, historical=True)
    values = {i: view.get(i, field_name) for i in wanted}
    return {
        i: float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None
        for i, v in values.items()
    }
