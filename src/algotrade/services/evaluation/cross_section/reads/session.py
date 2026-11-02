"""The reads of the edge harness that are made once per decision session, whatever the horizon or
the edge variant (ADR 0053, ADR 0063): ``SessionReads`` caches each screener's run, the regime
label, the eligible names per universe, the implied vol, the ADV and the scored outcomes until a
chunk of sessions is released; ``implied_at`` reads the implied vol of names at one session, for
the harness and the paper record alike."""

from collections.abc import Callable, Iterable, Sequence
from contextlib import AbstractContextManager
from dataclasses import replace
from datetime import date
from typing import TYPE_CHECKING

import pandas as pd

from algotrade.config.edges.document import Edge
from algotrade.config.edges.positions.chain import CHAIN_KIND
from algotrade.config.edges.verdict import OPTION_LEVELS, OptionCosts
from algotrade.config.strategy.schema import Selection
from algotrade.core.model.errors import MissingDataError
from algotrade.core.model.fields import REFERENCE_TABLE
from algotrade.core.views.market_features import MARKET_FEATURES
from algotrade.data import StoreReader
from algotrade.data.listings.membership import TABLE as MEMBERSHIP_TABLE
from algotrade.data.listings.universe import TABLE as LISTING_TABLE
from algotrade.data.rates import curve
from algotrade.data.reference import UNIVERSE_TABLE, resolver
from algotrade.services.evaluation.cross_section.historical import (
    HistoricalCaveat,
    IdentityTally,
)
from algotrade.services.evaluation.cross_section.hit import (
    apply_outcome,
    is_return,
    level_outcomes,
)
from algotrade.services.evaluation.cross_section.legs.rows import DayReads
from algotrade.services.evaluation.cross_section.picks import (
    RankedRun,
    SelectionReads,
    screen_variant,
)
from algotrade.services.evaluation.cross_section.reads.screens import CachedScreen, ScreenCache
from algotrade.services.licences import HARNESS_ALL
from algotrade.services.screening.regime import session_market
from algotrade.services.selection import fields_view

if TYPE_CHECKING:
    from algotrade.services.evaluation.cross_section.measuring import Variant

UNKNOWN = "UNKNOWN"
SECTOR_FIELD = "instrument.sector"  # the stratum of a pick's sector-matched random draws (ADR 0053)
ADV_FIELD = "rollup.price_stats@v2.adv_usd_20d"  # a pick's liquidity at D (leg v2, ADR 0064)
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

    def __init__(
        self,
        reader: StoreReader,
        label_field: str,
        screens: ScreenCache | None = None,
        owner: str = "",
    ):
        self._reader, self._label_field = reader.recording(), label_field
        self._screens, self._owner = screens, owner
        self._selections = SelectionReads(self._reader)
        self._runs: dict[tuple[str, date], RankedRun | None] = {}
        self._eligible: dict[tuple[str, date], frozenset[str]] = {}  # (universe repr, D)
        self._labels: dict[date, str] = {}
        self._implied: dict[tuple[str, frozenset[str], date], dict[str, float | None]] = {}
        self._adv: dict[tuple[frozenset[str], date], dict[str, float | None]] = {}
        self._siblings: dict[tuple[str, frozenset[str], date], dict[str, str | None]] = {}
        self._sectors: dict[tuple[frozenset[str], date], dict[str, str | None]] = {}
        self._numbers: dict[tuple[str, frozenset[str], date], dict[str, float | None]] = {}
        self._bills: dict[date, float | None] = {}
        self._history: dict[tuple[date, str, frozenset[str], date], dict[str, float | None]] = {}
        self._tickers: dict[tuple[tuple[str, ...], date], dict[str, str | None]] = {}
        self._outcomes: dict[tuple[str, int, date], pd.DataFrame] = {}
        self._levels: dict[tuple[str, int, date], list[pd.DataFrame]] = {}
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

    def adopt(self, reads: DayReads, snapshots: Iterable[date]) -> None:
        """Take over a session a run did not compute (its legs were reused): what it read counts
        in the run's historical caveat and universe snapshots as if it had."""
        for kind, counts in (("eligible", reads.eligible), ("screened", reads.screened)):
            self._identity.note(kind, reads.day, counts)
        self._snapshots.update(snapshots)

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
        digest = variant.config.hash
        cached = self._screens.get(self._owner, digest, day) if self._screens is not None else None
        if cached is not None:  # another edge of this run screened the config at this session
            self._reader.replay(day, cached.reads)
            found = cached.run
        else:
            try:
                with self._reader.capture(day) as reads:
                    found = screen_variant(self._reader, variant.config, day)
            except MissingDataError as error:
                if (
                    error.dataset in WIRING_DATASETS
                ):  # not an input the screener lacks: a broken run
                    raise
                self.lost[variant.id, day] = error.dataset
                self.errors.setdefault(variant.id, error)
                return None
            if self._screens is not None:
                self._screens.put(self._owner, digest, day, CachedScreen(found, reads))
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
        self._adv.clear()
        self._siblings.clear()
        self._sectors.clear()
        self._numbers.clear()
        self._history.clear()
        self._bills.clear()
        self._tickers.clear()
        self._outcomes.clear()
        self._levels.clear()

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

    def siblings(self, field_name: str, ids: frozenset[str], day: date) -> dict[str, str | None]:
        """The sibling id ``field_name`` gives each of ``ids`` read at D (None: not stored), through
        the recording reader: a restated reference partition invalidates the legs that read it,
        and a sibling that changed is the one D saw, never today's (EB H9)."""
        key = (field_name, ids, day)
        if key not in self._siblings:
            self._siblings[key] = strings_at(self._reader, field_name, ids, day)
        return self._siblings[key]

    def adv(self, ids: frozenset[str], day: date) -> dict[str, float | None]:
        """``adv_usd_20d`` of ``ids`` at D (None: not stored, never 0), read once per eligible
        set and session through the recording reader, so a restated liquidity partition
        invalidates the legs that read it (ADR 0063 decision 2, ADR 0064 decision 4)."""
        key = (ids, day)
        if key not in self._adv:
            self._adv[key] = numbers_at(self._reader, ADV_FIELD, ids, day)
        return self._adv[key]

    def numbers(self, field_name: str, ids: frozenset[str], day: date) -> dict[str, float | None]:
        """The declared numeric feature ``field_name`` of ``ids`` at D (None: not stored, never
        0), read once per set and session through the recording reader (a portfolio book's
        volatility, ADR 0074)."""
        key = (field_name, ids, day)
        if key not in self._numbers:
            self._numbers[key] = numbers_at(self._reader, field_name, ids, day)
        return self._numbers[key]

    def history(
        self, field_name: str, ids: frozenset[str], days: Sequence[date], decision: date
    ) -> dict[date, dict[str, float | None]]:
        """``field_name`` of ``ids`` as each of ``days`` read it (the value known at that day, not
        the latest), for the book of decision session ``decision``. Read through the recording
        reader and cached per decision session, never across them: a cache hit logs no read, so
        a later decision session sharing a day with this window would otherwise lose the partitions
        it depends on and keep a stale leg after a restatement (ADR 0074 amendment, item 15)."""
        out: dict[date, dict[str, float | None]] = {}
        for day in days:
            key = (decision, field_name, ids, day)
            if key not in self._history:
                self._history[key] = numbers_at(self._reader, field_name, ids, day)
            out[day] = self._history[key]
        return out

    def bill_yield(self, day: date) -> float | None:
        """The shortest-tenor Treasury bill yield (a decimal per year) of the curve ``day`` sees,
        the latest stored on or before it (``data.rates``: known at D); None when no curve is
        stored or the day is before the first one. What cash earns in a portfolio book (0074)."""
        if day not in self._bills:
            try:
                found = curve(self._reader, day)
            except MissingDataError:
                self._bills[day] = None
            else:  # before the first curve the read falls back to a LATER one: not known at D
                ok = len(found.frame) and not found.pre_snapshot
                self._bills[day] = float(found.frame["rate_par"].iloc[0]) if ok else None
        return self._bills[day]

    def instruments(self, tickers: tuple[str, ...], on: date) -> dict[str, str | None]:
        """The instrument id each ticker names in the reference snapshot ``on`` sees (None: the
        snapshot does not know it): how the benchmark's constituents are found, only through the
        resolver (ADR 0018), never built."""
        key = (tickers, on)
        if key not in self._tickers:
            found = resolver(self._reader, on)
            self._tickers[key] = {t: found.id_for(t) if found.knows(t) else None for t in tickers}
        return self._tickers[key]

    def sectors(self, ids: frozenset[str], day: date) -> dict[str, str | None]:
        """``instrument.sector`` of ``ids`` at D (None: not stored), read once per set and session
        through the recording reader, so a restated company snapshot invalidates the legs whose
        stratified draws read it (ADR 0063 decision 2)."""
        key = (ids, day)
        if key not in self._sectors:
            self._sectors[key] = labels_at(self._reader, SECTOR_FIELD, ids, day)
        return self._sectors[key]

    def outcomes(
        self, scope: str, horizon: int, day: date, score: Callable[[], pd.DataFrame]
    ) -> pd.DataFrame:
        """``score()`` once per (scope, horizon, D) in a chunk: every screener, baseline and the
        random draws of a scope score the same outcome rows (the frame is never changed)."""
        key = (scope, horizon, day)
        if key not in self._outcomes:
            self._outcomes[key] = score()
        return self._outcomes[key]

    def level_frames(
        self,
        scope: str,
        edge: Edge,
        horizon: int,
        day: date,
        rows: pd.DataFrame,
        ids: frozenset[str],
        costs: Sequence[float],
        option_costs: OptionCosts | None,
    ) -> list[pd.DataFrame]:
        """The outcomes of each base name at each level of the cost grid (the round trip at that
        many bp instead of ``cost_bps``; ADR 0064 decision 5) or, for an ``option_pnl`` edge, at
        each ``OPTION_LEVELS`` one (``hit.level_outcomes``); none for any other outcome.
        Exclusions do not depend on the cost, so the counted names are the session's own. Kept
        like ``outcomes``, once per (scope, horizon, D) in a chunk."""
        if edge.outcome.kind == CHAIN_KIND:
            if option_costs is None:
                return []
            key = (scope, horizon, day)
            if key not in self._levels:
                inside = rows[rows["instrument_id"].isin(ids)]
                done = level_outcomes(edge, inside, OPTION_LEVELS, option_costs)
                self._levels[key] = [f.set_index("instrument_id") for f in done]
            return self._levels[key]
        if not is_return(edge):
            return []
        found = []
        for level in costs:
            costed = replace(edge, outcome=replace(edge.outcome, cost_bps=level))

            def score(e: Edge = costed) -> pd.DataFrame:
                inside = rows[rows["instrument_id"].isin(ids)]
                return apply_outcome(e, inside).set_index("instrument_id")

            found.append(self.outcomes(f"{scope}@{level:g}bp", horizon, day, score))
        return found


def implied_at(
    reader: StoreReader, field_name: str, ids: Iterable[str], day: date
) -> dict[str, float | None]:
    """The implied vol ``field_name`` of ``ids`` read at the decision session ``day`` (None: not
    stored): what an ``expires_otm`` strike or a vol ratio is measured from, for the harness and
    the paper record alike."""
    return numbers_at(reader, field_name, ids, day)


def labels_at(
    reader: StoreReader, field_name: str, ids: Iterable[str], day: date
) -> dict[str, str | None]:
    """The text field ``field_name`` of ``ids`` read at ``day`` (None: not stored or empty)."""
    wanted = sorted(ids)
    view, _ = fields_view(reader, (field_name,), day, wanted, historical=True, held=HARNESS_ALL)
    values = {i: view.get(i, field_name) for i in wanted}
    return {i: v if isinstance(v, str) and v else None for i, v in values.items()}


def numbers_at(
    reader: StoreReader, field_name: str, ids: Iterable[str], day: date
) -> dict[str, float | None]:
    """The numeric field ``field_name`` of ``ids`` read at ``day`` (None: not stored or not a
    number)."""
    wanted = sorted(ids)
    view, _ = fields_view(reader, (field_name,), day, wanted, historical=True, held=HARNESS_ALL)
    values = {i: view.get(i, field_name) for i in wanted}
    return {
        i: float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None
        for i, v in values.items()
    }


def strings_at(
    reader: StoreReader, field_name: str, ids: Iterable[str], day: date
) -> dict[str, str | None]:
    """The text field ``field_name`` of ``ids`` read at ``day`` (None: not stored or not text)."""
    wanted = sorted(ids)
    view, _ = fields_view(reader, (field_name,), day, wanted, historical=True, held=HARNESS_ALL)
    values = {i: view.get(i, field_name) for i in wanted}
    return {i: v if isinstance(v, str) and v else None for i, v in values.items()}
