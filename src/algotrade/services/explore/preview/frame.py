"""The field frame a preview evaluates: every instrument known on the session with the fields
its selection and spec read (column-pruned, through ``services.selection.fields_view``), plus
the universe snapshot. Kept in a small in-process LRU keyed by (session, field set, the user
features read, ``StoreReader.visible_seq()``), so threshold / mode / tolerance edits
re-evaluate in memory and a new publish (ADR 0022) is never served stale."""

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from datetime import date
from functools import cached_property

from algotrade.config.site.settings import FeatureDefinition
from algotrade.config.strategy.schema import Selection
from algotrade.core.views.feature_view import FeatureView
from algotrade.data import StoreReader
from algotrade.data.reference import Universe, load_universe
from algotrade.engines.selection.evaluate import SelectionResult, evaluate_selection
from algotrade.features.expressions.feature_set import FeatureSet
from algotrade.services.explore.store import ResultCache
from algotrade.services.selection import fields_view
from algotrade.services.views import to_value
from algotrade.strategies.screeners.rules.evaluate import ScreenMemo

PREVIEW = "preview"
MAX_MEMO = 64  # criteria (selections) whose results a frame keeps: a few edits of a few screens


@dataclass(frozen=True)
class FieldFrame:
    view: FeatureView  # every instrument known on the session, keyed by catalogue field
    universe: Universe
    missing: tuple[str, ...]  # tables read with no rows for the session (their fields UNKNOWN)
    pre_snapshot: bool  # the reference snapshot is after the session (survivorship)
    # Criterion results over ``view`` (``evaluate_screen``'s memo): an edit to one criterion
    # re-evaluates only that one. Bounded by ``MAX_MEMO`` criteria (``memo_for``).
    memo: ScreenMemo = field(default_factory=dict, compare=False, repr=False)
    selections: dict[Selection, SelectionResult] = field(
        default_factory=dict, compare=False, repr=False
    )

    def selected(self, selection: Selection) -> SelectionResult:
        """``selection`` over ``view`` (memoised: criteria edits keep the selection)."""
        found = self.selections.get(selection)
        if found is None:
            if len(self.selections) >= MAX_MEMO:
                self.selections.clear()
            found = replace(
                evaluate_selection(selection, self.view),
                missing_tables=self.missing,
                pre_snapshot=self.pre_snapshot,
            )
            self.selections[selection] = found
        return found

    @cached_property
    def symbols(self) -> dict[str, str]:
        """Ticker by instrument id (from the universe snapshot), built once per frame."""
        frame = self.universe.frame
        if "symbol" not in frame:
            return {}
        pairs = zip(frame["instrument_id"].astype(str), frame["symbol"], strict=True)
        return {i: str(s) for i, s in pairs if to_value(s) is not None}

    @cached_property
    def names(self) -> dict[str, str]:
        """Company or fund name by instrument id (from the universe snapshot), built once."""
        frame = self.universe.frame
        if "company_name" not in frame:
            return {}
        pairs = zip(frame["instrument_id"].astype(str), frame["company_name"], strict=True)
        return {i: str(n) for i, n in pairs if to_value(n) is not None}

    def memo_for(self) -> ScreenMemo:
        """The memo, emptied first once it holds ``MAX_MEMO`` criteria (many edits)."""
        if len(self.memo) >= MAX_MEMO:
            self.memo.clear()
        return self.memo


def features_key(definitions: Sequence[FeatureDefinition]) -> str:
    """The user features a screen reads, as a digest: an edited formula is a new entry."""
    text = repr([d.canonical() | {"name": d.name, "owner": d.owner} for d in definitions])
    return hashlib.sha256(text.encode()).hexdigest()


def field_frame(
    reader: StoreReader,
    cache: ResultCache,
    session: date,
    fields: Sequence[str],
    features: FeatureSet,
    definitions: Sequence[FeatureDefinition],
) -> tuple[FieldFrame, bool]:
    """The frame for ``fields`` on ``session`` and whether it came from the cache. The commit
    sequence is read before reading, so a publish landing meanwhile stores the frame under
    the older key, which no later call asks for."""
    wanted = tuple(sorted(set(fields)))
    key = (PREVIEW, session, wanted, features_key(definitions), reader.visible_seq())
    hit = cache.get(key)
    if hit is not None:
        return hit, True
    view, source = fields_view(reader, wanted, session, features=features)
    built = FieldFrame(view, load_universe(reader, session), source.missing, source.pre_snapshot)
    cache.put(key, built)
    return built, False
