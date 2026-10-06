"""Coverage acceptance (ADR 0043): per key feature and tier, the share of the instruments the
feature APPLIES to that have a value for the session, graded against ``sources.toml
[quality.coverage.*]`` (a minimum per tier and a largest day-over-day drop), so a silent gap
(515 optionable names with no ``iv30``; two S&P 500 members with no earnings row) fails or
warns instead of passing.

Only the session's own partitions are read (ADR 0036; a table with none has every applicable
name missing). Applicability is ``Feature.applies_to`` decided by ``features.framework.feature
.not_applicable``, the function the read layer's NOT_APPLICABLE uses (ADR 0042), over the
session's reference snapshot; the population is the universe snapshot of the session; tiers are
``tasks.market.tiers`` (core: S&P 500, priority symbols, HIGH liquidity). A value is covered when
present, or null for a reason the feature declares as "too illiquid to price" (ADR 0042: not a
gap); any other missing value is missing, never counted as zero or filled. The previous
session's shares are recomputed from its stored partitions (no new table); the nightly runs
this as the acceptance check of ``rollups`` and ``run_quality`` runs it with the rest.
"""

from dataclasses import dataclass
from datetime import date
from typing import Any

import pandas as pd

from algotrade.config.site.coverage import CoverageRule
from algotrade.config.site.settings import SourcesSettings
from algotrade.core.model.fields import REFERENCE_TABLE
from algotrade.data import StoreReader
from algotrade.data.reference import UNIVERSE_TABLE, snapshot
from algotrade.features.expressions.feature_set import FeatureSet
from algotrade.features.framework.feature import Feature, not_applicable
from algotrade.services.features import site_features, site_store
from algotrade_ingestion.tasks.maintenance.quality import Check
from algotrade_ingestion.tasks.market.tiers import CORE, REST, load_tiers

TIERS = (CORE, REST)
STORED_EXAMPLES = 10  # missing names kept per cell in the check's data (the email shows fewer)
ETF = "ETF"


@dataclass(frozen=True)
class Cell:
    """One feature in one tier for one session: ``covered`` of ``applicable`` names have it."""

    feature: str
    tier: str
    applicable: int
    covered: int
    missing: tuple[str, ...]  # symbols, sorted, at most STORED_EXAMPLES

    @property
    def share(self) -> float | None:
        """``None`` when nothing applies (no gap to speak of), else covered / applicable."""
        return self.covered / self.applicable if self.applicable else None


def _population(reader: StoreReader, session: date) -> pd.DataFrame | None:
    """The universe of the session (instrument_id, symbol, optionable, is_etf) with the
    reference snapshot's facts: ``None`` when there is no universe or reference snapshot on or
    before the session."""
    uni, ref = snapshot(reader, UNIVERSE_TABLE, session), snapshot(reader, REFERENCE_TABLE, session)
    if uni is None or ref is None or uni.pre_snapshot or ref.pre_snapshot:
        return None
    ids = reader.table(UNIVERSE_TABLE, uni.snapshot_date)
    facts = reader.table(REFERENCE_TABLE, ref.snapshot_date)
    if ids is None or facts is None:
        return None
    pop = (
        ids[["instrument_id"]]
        .drop_duplicates()
        .merge(
            facts[["instrument_id", "symbol", "security_type", "optionable"]],
            on="instrument_id",
            how="left",
        )
    )
    pop["is_etf"] = pop["security_type"].astype(str) == ETF
    pop["optionable"] = pop["optionable"].map(lambda v: None if pd.isna(v) else bool(v))
    return pop


def _illiquid(stored: pd.DataFrame, feat: Feature) -> pd.Series:
    """Rows whose null is explained as an illiquid chain by the feature's own sibling status
    column (ADR 0042 reads these as ILLIQUID, not as a gap)."""
    status = feat.null_status
    if not status or "@" in status or status not in stored.columns:
        return pd.Series(False, index=stored.index)
    return stored[status].isin(feat.illiquid_statuses)


def _locate(fs: FeatureSet, feature: str) -> tuple[str, str, Feature]:
    """``<group>.<column>`` -> its stored table, column and declaration."""
    group, _, column = feature.partition(".")
    found = [
        f for f in fs.features.values() if f.group.partition("@")[0] == group and f.name == column
    ]
    if not found:
        raise ValueError(f"coverage: {feature!r} is not a stored feature of the catalogue")
    return fs.table(group), column, found[0]


def cells(
    reader: StoreReader,
    day: date,
    rules: tuple[CoverageRule, ...],
    priority_symbols: tuple[str, ...],
    fs: FeatureSet,
) -> list[Cell] | None:
    """Every rule's cells (core, rest) for ``day``; ``None`` without a universe to measure."""
    pop = _population(reader, day)
    if pop is None:
        return None
    tiers = load_tiers(reader, day, priority_symbols)
    symbols = pop["symbol"].astype(str).to_numpy()
    pop = pop.assign(
        tier=[
            tiers.tier(i, s) for i, s in zip(pop["instrument_id"].astype(str), symbols, strict=True)
        ]
    )
    out: list[Cell] = []
    for rule in rules:
        table, column, feat = _locate(fs, rule.feature)
        stored = reader.table(table, day)
        if stored is None or column not in stored.columns:
            have: set[str] = set()
        elif rule.covered_by == "row":
            have = set(stored["instrument_id"].astype(str))
        else:
            explained = _illiquid(stored, feat)
            have = set(stored.loc[stored[column].notna() | explained, "instrument_id"].astype(str))
        applies = [
            not not_applicable([feat.applies_to], opt, etf)
            for opt, etf in zip(pop["optionable"], pop["is_etf"], strict=True)
        ]
        for tier in TIERS:
            mine = pop[(pop["tier"] == tier) & pd.Series(applies, index=pop.index)]
            ids = mine["instrument_id"].astype(str)
            gone = mine.loc[~ids.isin(have), "symbol"].astype(str)
            out.append(
                Cell(
                    rule.feature,
                    tier,
                    len(mine),
                    len(mine) - len(gone),
                    tuple(sorted(gone))[:STORED_EXAMPLES],
                )
            )
    return out


def _previous(
    reader: StoreReader, session: date, fs: FeatureSet, rules: tuple[CoverageRule, ...]
) -> date | None:
    """The latest session before ``session`` that has partitions of the rules' tables."""
    days = [d for r in rules for d in reader.dates(_locate(fs, r.feature)[0]) if d < session]
    return max(days) if days else None


def _percent(share: float | None) -> str:
    return "n/a" if share is None else f"{share:.1%}"


def check_coverage(reader: StoreReader, session: date, s: SourcesSettings) -> list[Check]:
    """One check per configured feature: FAIL / WARN (by the rule's level) when a tier's
    share is under its minimum or fell more than ``max_drop`` since the previous session,
    else PASS. ``data`` carries the cells (and the previous shares) for the report."""
    fs = site_features(site_store(None))
    today = cells(reader, session, s.coverage, s.cboe_priority_symbols, fs)
    if today is None:
        return [Check("coverage", "FAIL", "no universe or reference snapshot to measure against")]
    before_day = _previous(reader, session, fs, s.coverage)
    before = (
        cells(reader, before_day, s.coverage, s.cboe_priority_symbols, fs) if before_day else None
    )
    prev = {(c.feature, c.tier): c.share for c in before or []}
    checks = []
    for rule in s.coverage:
        mine = [c for c in today if c.feature == rule.feature]
        status, notes = "PASS", []
        rows: list[dict[str, Any]] = []
        for c in mine:
            floor = rule.core_min if c.tier == CORE else rule.rest_min
            share, was = c.share, prev.get((c.feature, c.tier))
            breaches = []
            if share is not None and share < floor:
                breaches.append(f"{_percent(share)} < min {floor:.0%}")
            if share is not None and was is not None and was - share > rule.max_drop:
                breaches.append(f"fell {was - share:.1%} from {_percent(was)}")
            if breaches:
                notes.append(f"{c.tier} {'; '.join(breaches)}")
                level = rule.level_of(c.tier)
                status = "FAIL" if "FAIL" in (status, level) else "WARN"
            rows.append(
                {
                    "tier": c.tier,
                    "applicable": c.applicable,
                    "covered": c.covered,
                    "share": share,
                    "previous": was,
                    "ok": not breaches,
                    "missing": list(c.missing),
                }
            )
        figures = ", ".join(f"{c.tier} {_percent(c.share)} of {c.applicable}" for c in mine)
        detail = f"{figures}" + (f" ({'; '.join(notes)})" if notes else "")
        checks.append(
            Check(
                f"coverage_{rule.feature}",
                status,
                detail,
                data={"cells": rows, "previous_session": str(before_day) if before_day else ""},
            )
        )
    return checks
